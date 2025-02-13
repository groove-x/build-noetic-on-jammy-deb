set -xeu
repo_path=$1
pkg_name=$2
export DEB_BUILD_OPTIONS="parallel=$(nproc)"

cd $repo_path
for xml_path in $(find . -name package.xml); do
  xml_pkg=$(xmllint --xpath /package/name $xml_path | sed 's/^.*<name.*>\(.*\)<\/name>.*$/\1/g')
  if [ "$xml_pkg" = "$pkg_name" ]; then
    pkg_path=$(dirname $xml_path)
    cd $pkg_path
    # 既存のビルドファイルを削除
    rm -rf debian .obj*
    # shared_mutex, shared_lock 等への対策 (c++17) にする
    sed -i -e 's/\+\+\(11\|14\)/++17/g' CMakeLists.txt
    sed -i -e 's/CMAKE_CXX_STANDARD \(11\|14\)/CMAKE_CXX_STANDARD 17/g' CMakeLists.txt

    bloom-generate rosdebian --os-name ubuntu --os-version noble --ros-distro noetic
    # catkinパッケージに setup.bash 等を含めるための対策
    if [ "$pkg_name" = "catkin" ]; then
      sed -i -e 's/CATKIN_BUILD_BINARY_PACKAGE="1"/CATKIN_BUILD_BINARY_PACKAGE="0"/g' debian/rules
    fi
    fakeroot debian/rules "binary --parallel"
    cd .. && apt-get install --no-install-recommends -y ./ros-noetic-*.deb || exit 1
    mv ./ros-noetic-*.deb /tmp/deb
    break
  fi
done
