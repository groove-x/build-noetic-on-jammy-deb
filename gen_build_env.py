from urllib.parse import urlparse
from pathlib import Path
import requests
import yaml
import coloredlogs, logging
from xml.etree import ElementTree
from argparse import ArgumentParser
from pprint import pformat
from typing import List, Set
from packaging import version
from dataclasses import dataclass, field

coloredlogs.install(level="INFO")
logger = logging.getLogger(__name__)

@dataclass
class MakefileTarget:
    target: str
    depends: List[str] = field(default_factory=list)
    commands: List[str] = field(default_factory=list)
    comment: str = ""
    phony: bool = False
    alias: str = None

    def __str__(self):
        makefile_string = ""
        if self.comment:
            makefile_string += f"# {self.comment}\n"

        if self.alias:
            makefile_string += f".PHONY: {self.alias}\n"
            makefile_string += f"{self.alias}: {self.target}\n\n"

        if self.phony:
            makefile_string += f".PHONY: {self.target}\n"
        makefile_string += f"{self.target}:"
        if self.depends:
            makefile_string += f" {' '.join(self.depends)}\n"
        else:
            makefile_string += "\n"
        for cmd in self.commands:
            makefile_string += f"\t{cmd}\n"

        return makefile_string

@dataclass
class GitRepository:
    name: str
    url: str
    base_dir: Path=Path(".")
    branch: str=None
    recursive: bool=True

    @property
    def makefile_target(self) -> MakefileTarget:
        clone_cmd = f"git clone {self.url} `dirname $@`"
        if self.branch:
            clone_cmd += f" -b {self.branch}"
        if self.recursive:
            clone_cmd += " --recursive"
        target = MakefileTarget(
            target=str(self.base_dir / self.name / ".git"),
            commands=[clone_cmd]
        )
        return target

    @property
    def repo_dir(self) -> Path:
        return self.base_dir / self.name


@dataclass
class BuildPackage:
    target: MakefileTarget
    repo: GitRepository

    def __post_init__(self):
        self.target.depends.insert(0, self.repo.makefile_target.target)

    @property
    def makefile_targets(self) -> List[MakefileTarget]:
        targets = [
            self.repo.makefile_target,
            self.target]
        return targets


class BuildFarm(object):
    rosdistro_base_url = "https://raw.githubusercontent.com/ros/rosdistro/master"
    index_path = Path("index-v4.yaml")
    base_path = Path("rosdep/base.yaml")
    python_path = Path("rosdep/python.yaml")
    cache_dir = Path("cache")
    cache_dir.mkdir(exist_ok=True, parents=True)

    def __init__(self, ros_distribution="noetic", ubuntu_distribution="jammy"):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ros_distribution = ros_distribution
        self.ubuntu_distribution = ubuntu_distribution
        self.os_name = "ubuntu"
        self.python_exec = "python3"

        self.__dist_index = None
        self.__dist_info = None
        self.__dist_cache = None
        self.__dist_base = None
        self.__dist_python = None

    @property
    def dist_index(self):
        if self.__dist_index is None:
            url = f"{self.rosdistro_base_url}/{self.index_path}"
            self.logger.debug(f"Loading rosdep index from {url}")
            self.__dist_index = self.get_rosdep_yaml(url)
        return self.__dist_index

    @property
    def dist_info(self):
        if self.__dist_info is None:
            dist_path = self.dist_index["distributions"][self.ros_distribution]["distribution"]
            if len(dist_path) != 1:
                raise RuntimeError(f"Multiple distribution path not supported: {dist_path}")

            dist_url = f"{self.rosdistro_base_url}/{dist_path[0]}"
            self.logger.debug(f"Loading rosdep info from {dist_url}")
            self.__dist_info = self.get_rosdep_yaml(dist_url)
        return self.__dist_info

    @property
    def dist_cache(self):
        if self.__dist_cache is None:
            cache_url = self.dist_index["distributions"][self.ros_distribution]["distribution_cache"]
            self.logger.debug(f"Loading rosdep cache from {cache_url}")
            self.__dist_cache = self.get_rosdep_yaml(cache_url)
        return self.__dist_cache

    @property
    def dist_base(self):
        if self.__dist_base is None:
            url = f"{self.rosdistro_base_url}/{self.base_path}"
            self.logger.debug(f"Loading rosdep base from {url}")
            self.__dist_base = self.get_rosdep_yaml(url)
        return self.__dist_base

    @property
    def dist_python(self):
        if self.__dist_python is None:
            url = f"{self.rosdistro_base_url}/{self.python_path}"
            self.logger.debug(f"Loading rosdep base from {url}")
            self.__dist_python = self.get_rosdep_yaml(url)
        return self.__dist_python

    def get_rosdep_yaml(self, url: str, load_cache=True, save_cache=True):
        res = urlparse(url)
        path = Path(res.path)
        if path.suffix in [".yaml", ".yml"]:
            filename = path.name
        elif path.suffix == ".gz":
            filename = path.stem
        else:
            raise RuntimeError(f"Unknown file extension: {path.suffix}")
        cachepath = self.cache_dir / filename
        if cachepath.exists() and load_cache:
            with cachepath.open() as f:
                content = yaml.safe_load(f)
                self.logger.debug(f"Load data from cache: {cachepath}")
                return content

        self.logger.debug(f"Load data from URL: {url}")
        res = requests.get(url, allow_redirects=True)
        if path.suffix in [".yaml", ".yml"]:
            content = yaml.safe_load(res.content.decode("utf-8"))
        elif path.suffix == ".gz":
            # ungzip from response
            import gzip
            import io
            content = gzip.GzipFile(fileobj=io.BytesIO(res.content)).read()
            content = yaml.safe_load(content)

        if save_cache:
            with cachepath.open("w") as f:
                yaml.safe_dump(content, f)
                self.logger.debug(f"rosdep yaml saved to cache: {cachepath}")
        return content

    def get_repository(self, package_name: str):
        name = None
        repository = None
        for k, v in self.dist_cache["distribution_file"][0]["repositories"].items():
            if package_name in v.get("release", {}).get("packages", [k]):
                name = k
                repository = v
                self.logger.debug(f"package {package_name} found in {k}")
                break
        return name, repository

    def get_xml_data_by_tags(self, package_name: str, tags: List[str]):
        data = []

        if package_name not in self.dist_cache["release_package_xmls"]:
            return data

        xml = self.dist_cache["release_package_xmls"][package_name]

        root = ElementTree.fromstring(xml)
        for child in root:
            if child.tag in tags:
                data.append({
                    "tag": child.tag,
                    "text": child.text,
                    "attrib": child.attrib})
        return data

    def get_package_version(self, package_name: str):
        try:
            return self.get_xml_data_by_tags(package_name, ["version"])[0]["text"]
        except:
            self.logger.debug(f"package version for {package_name} is not found.")
            return None

    def get_dependencies(self, package_name: str):
        tags_for_dependencies = [
            "depend",
            "build_depend",
            "buildtool_depend",
            "run_depend",
            "exec_depend",
            "build_export_depend",
            "test_depend",
        ]
        depends = self.get_xml_data_by_tags(package_name, tags_for_dependencies)
        return depends

    def get_package_dependencies(self, package_name: str, ignore_depends: Set[str]=set(), recursive=True):
        depends_xml = self.get_dependencies(package_name)

        depends = set()
        for d in depends_xml:
            dep_name = d["text"]
            depends.add(dep_name)
            if "attrib" in d:
                # check attributes
                for k, v in d["attrib"].items():
                    if k == "condition":
                        if v.split(" ")[-1] != "3":
                            depends.remove(dep_name)
                            continue
                    if k == "version_gte":
                        package_version = self.get_package_version(dep_name)
                        if package_version is None:
                            continue
                        if version.parse(v) >= version.parse(package_version):
                            self.logger.warning(f"{dep_name} required version_gte {v} by {package_name} but {package_version}")
                            self.logger.debug(d)
                    elif k == "version_gt":
                        package_version = self.get_package_version(dep_name)
                        if package_version is None:
                            continue
                        if version.parse(v) > version.parse(package_version):
                            self.logger.warning(f"{dep_name} required version_gte {v} by {package_name} but {package_version}")
                            self.logger.debug(d)
                    elif k == "condition":
                        pass
                    else:
                        self.logger.warning(f"unknown attribute {k}: {v} in depends {dep_name}")
                        self.logger.debug(d)

        if recursive:
            for key in list(depends):
                if key not in ignore_depends:
                    child = self.get_package_dependencies(key, depends)
                    depends.update(child)

        return depends

    def get_package_names(self, base_dep: Set[str], python_dep: Set[str]):
        base_pkgs = [self.dist_base[n].get("ubuntu") for n in base_dep]
        python_pkgs = [self.dist_python[n].get("ubuntu") for n in python_dep]

        pkg_infos = base_pkgs + python_pkgs
        pkgs = set()
        for p in pkg_infos:
            if isinstance(p, list):
                pkgs.update(p)
            elif isinstance(p, dict):
                if self.ubuntu_distribution in p:
                    pkgs.update(p[self.ubuntu_distribution])
                elif "*" in p:
                    if p["*"] is not None:
                        pkgs.update(p["*"])
                else:
                    self.logger.warning(f"package names not found for {self.ubuntu_distribution}: {p}")
            else:
                self.logger.warning("unknown package name format")

        return pkgs

    def classify_packages(self, packages: Set[str]):
        # find depends that are not in rosdistro
        base_keys = set(self.dist_base.keys())
        python_keys = set(self.dist_python.keys())
        base_packages = base_keys & packages
        python_packages = python_keys & packages
        build_packages = packages - base_packages - python_packages

        return base_packages, python_packages, build_packages

    def gen_rosdep_yaml(self, rosdep_yaml: Path, targets: Set[str]):
        rosdep_data = {}
        for target in targets:
            rosdep_data[target] = {"ubuntu": f"ros-noetic-{target.replace('_', '-')}"}
        with rosdep_yaml.open("w") as f:
            yaml.safe_dump(rosdep_data, f)

    def gen_makefile(self, makefile: Path, main_targets: set, build_dep: Set[str]):
        build_dir = Path(f"/root/{self.ros_distribution}_build/src")

        makefile_targets = []

        # main target
        makefile_targets += [
            "# main target",
            MakefileTarget(
                target="all",
                depends=main_targets,
                commands=[
                    f"@echo built packages : `ls -1 /tmp/deb/* | wc -l` / {len(build_dep) + 8}"],
                phony=True)
        ]

        # build env
        # ディレクトリをターゲットにすると中に変更があったときに日付が更新されちゃう
        env_dep = [
            "/tmp/deb/.touch",
            "/tmp/built_packages/.touch",
            f"{build_dir}/.touch",
        ]
        makefile_targets += [
            "# build env",
            MakefileTarget(
                target="env_targets",
                depends=env_dep)]
        for env in env_dep:
            makefile_targets.append(MakefileTarget(
                target=env,
                commands=["mkdir -p $(shell dirname $@)", f"touch $@"]))

        # python tools for build
        makefile_targets.append("# python tools for build")
        makefile_targets += [
            MakefileTarget(
                target="python_tools",
                depends=["/root/.ros/rosdep/sources.cache"],
                phony=True),
            MakefileTarget(
                target="/etc/ros/rosdep/sources.list.d",
                depends=["/tmp/built_packages/rosdep"],
                commands=["rosdep init"]),
            MakefileTarget(
                target="/root/.ros/rosdep/sources.cache",
                depends=[
                    "/root/rosdep.yaml",
                    "/etc/ros/rosdep/sources.list.d"],
                commands=[
                    "echo \"yaml file:///root/rosdep.yaml\" > /etc/ros/rosdep/sources.list.d/99-custom.list",
                    "rosdep update"]),
        ]

        python_build_packages = [
            BuildPackage(
                target=MakefileTarget(
                    target="/usr/local/bin/ros_release_python",
                    commands=[f"ln -sf {build_dir}/ros_release_python/scripts/ros_release_python $@"]),
                repo=GitRepository(
                    name="ros_release_python",
                    url="https://github.com/ros-infrastructure/ros_release_python.git",
                    base_dir=build_dir))]
        python_packages = {
            "catkin_pkg": [],
            "rospkg": ["catkin_pkg"],
            "rosdistro": ["rospkg"],
            "rosdep": ["rosdistro"],
            # "bloom": [],
        }
        for pkg, dep in python_packages.items():
            target = MakefileTarget(
                target=f"/tmp/built_packages/{pkg.replace('_', '-')}",
                depends=["/usr/local/bin/ros_release_python"] + env_dep + [f"/tmp/built_packages/{d.replace('_', '-')}" for d in dep],
                commands=[f"cd `dirname $<` && ros_release_python deb3 && apt-get install -y ./deb_dist/*.deb && mv ./deb_dist/*.deb /tmp/deb && touch $@"])
            repo = GitRepository(
                name=pkg,
                url=f"https://github.com/ros-infrastructure/{pkg}.git",
                base_dir=build_dir)
            python_build_packages.append(BuildPackage(
                target=target, repo=repo))
        for pkg in python_build_packages:
            makefile_targets += pkg.makefile_targets

        # packages to build
        makefile_targets.append("# ROS packages to build")
        build_targets = []
        for target in build_dep:
            dependencies = self.get_package_dependencies(target, recursive=False) & build_dep
            repo_name, repo = self.get_repository(target)
            url = repo["source"]["url"]
            branch = repo["source"]["version"]

            # Compatibility fix for liblog4cxx v0.11-0.13
            # https://github.com/ros/rosconsole/pull/58
            # TODO: remove this when PR is merged
            if repo_name == "rosconsole":
                url = "https://github.com/twdragon/rosconsole.git"
                branch = "log4cxx-0.12"

            repository = GitRepository(
                name=repo_name,
                url=url,
                base_dir=build_dir,
                branch=branch)

            target = MakefileTarget(
                target=f"/tmp/built_packages/{target}",
                depends=[f"/tmp/built_packages/{d}" for d in list(dependencies)] + ["/root/.ros/rosdep/sources.cache"],
                commands=[f"bash build_ros_package.sh {repository.repo_dir} {target} && touch $@"],
                alias=target)
            build_targets.append(BuildPackage(
                target=target,
                repo=repository))

        for pkg in build_targets:
            makefile_targets += pkg.makefile_targets

        makefile_targets.append(MakefileTarget(
            target="clean",
            commands=[f"rm -rf /tmp/deb /tmp/built_packages {build_dir} /usr/local/bin/ros_release_python /etc/ros/rosdep/sources.list.d/20-default.list"],
            phony=True))

        with makefile.open("w") as f:
            wrote_targets = set()
            for target in makefile_targets:
                # skip duplicated targets
                # basically, it's happens on ROS packages git repository
                if isinstance(target, MakefileTarget):
                    if target.target in wrote_targets:
                        self.logger.debug(f"skip duplicated target: {target.target}")
                        continue
                    else:
                        wrote_targets.add(target.target)
                f.write(f"{target}\n")

    def gen_dockerfile(self, dockerfile: Path, apt_pkgs: set):
        required_packages_for_build = {
            "build-essential",
            "git",
            "dh-make",
            "dh-python",
            "libxml2-utils",
            "libturbojpeg0-dev",
            "vim",
            "python3-stdeb",
            "python3-dateutil",
            "python3-docutils",
            "python3-vcstools",
            "python3-packaging",
            "python3-pip",
        }

        # 自前ビルドするものや、jammy に用意されていないものを除外
        ignore_pkgs = {
            "python3-catkin-pkg",
            "python3-catkin-pkg-modules",
            "python3-rospkg",
            "python3-rospkg-modules",
            "python3-rosdistro",
            "python3-rosdistro-modules",
            "python3-rosdep",
            "python3-rosdep-modules",
        }
        install_apt_packages = list(required_packages_for_build | apt_pkgs - ignore_pkgs)
        install_apt_packages.sort()

        with dockerfile.open("w") as f:
            f.write(f"FROM ubuntu:{self.ubuntu_distribution}\n")
            f.write("ENV DEBIAN_FRONTEND=noninteractive\n")

            f.write("RUN apt-get update && apt-get upgrade -y && apt-get install -y \\\n  ")
            f.write(" \\\n  ".join(install_apt_packages) + "\n\n")

            # bloom がうまくビルドできなかったのでとりあえずpipで最新を入れる
            f.write("RUN pip3 install -U pip && pip3 install bloom\n")

            f.write("\n")

            f.write("COPY rosdep.yaml /root\n")
            f.write("COPY *.sh /root/\n")
            f.write("COPY Makefile /root/\n")

            f.write("\n")
            f.write("WORKDIR /root\n")

def parse_args():
    parser = ArgumentParser(description="Build debian package tool for Noetic on Jammy")
    parser.add_argument("--debug", action="store_true", help="enable debug message")
    parser.add_argument("--targets", nargs="*", default="desktop", help="target packages to build")
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()

    if args.debug:
        coloredlogs.install(level="DEBUG")

    bf = BuildFarm()

    # 依存関係を抽出
    all_depend_packages = set()
    for target in args.targets:
        all_depend_packages |= bf.get_package_dependencies(target)
    logger.info(f"all_depend_packages: {len(all_depend_packages)} packages")
    for package_name in pformat(all_depend_packages).split("\n"):
        logger.debug(f"  {package_name}")

    # aptで取得するものと、ビルドする必要があるものを分ける
    base_pkgs, python_pkgs, build_pkgs = bf.classify_packages(all_depend_packages)
    # ターゲットを追加
    build_pkgs |= set(args.targets)

    logger.info(f"base packages: {len(base_pkgs)} packages")
    for package_name in pformat(base_pkgs).split("\n"):
        logger.debug(f"  {package_name}")

    logger.info(f"python packages: {len(python_pkgs)} packages")
    for package_name in pformat(python_pkgs).split("\n"):
        logger.debug(f"  {package_name}")

    logger.info(f"build packages: {len(build_pkgs)} packages")
    for package_name in pformat(build_pkgs).split("\n"):
        logger.debug(f"  {package_name}")

    # base_depends to apt_depends
    apt_pkgs = bf.get_package_names(base_pkgs, python_pkgs)
    logger.info(f"apt packages: {len(apt_pkgs)} packages")
    for package_name in pformat(apt_pkgs).split("\n"):
        logger.debug(f"  {package_name}")

    # generate files for build
    base_path = Path("docker")
    base_path.mkdir(parents=True, exist_ok=True)
    rosdep_yaml = base_path / "rosdep.yaml"
    bf.gen_rosdep_yaml(rosdep_yaml, build_pkgs)
    makefile = base_path / "Makefile"
    bf.gen_makefile(makefile, set(args.targets), build_pkgs)
    dockerfile = base_path / "Dockerfile"
    bf.gen_dockerfile(dockerfile, apt_pkgs)
