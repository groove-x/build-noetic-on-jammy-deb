# build-noetic-on-jammy-deb

A tool to generate binary debian packages of [ROS 1 Noetic Ninjemys](http://wiki.ros.org/noetic) on Ubuntu 24.04 (Noble Numbat)

## 基本的な動作

- ビルド環境生成
- ROS Deb Package ビルドに必要なPython Tools の生成
- Target に関連する依存パッケージのビルド
- Target のパッケージのビルド

## Modifications for Noble Compatibility

- catkin
  - オプションを変更してsetup.bash等が生成されるようにしている
- c++17指定
  - c++11 等の指定になっている部分を c++17 に変更している
  - shared_mutex, shared_lock を使用するため
    - なぜかfocalではc++11指定でも使えたようである
- ros-noetic-simulation can't be built on Ubuntu 24.04 because of lack of gazebo packages
- Some repositories from ros-o project are used instead of the official ones
  - They provide some fixes for the packages, for example, for the python3.12 compatibility
  - Thanks to the ros-o project

## Build Instructions

```bash
# Generate build environment (Dockerfile, Makefile, rosdep.yaml, etc.)
make desktop
# Build the generated Docker image and login to the container
make login

# After logging in
# Build all the packages
make
```

## ファイルの取り出し手順

ビルド後の docker を落とさずに下記を別シェルで実行

```bash
# /tmp に deb ファイルが生成されるので、それを取り出す
docker ps -f "ancestor=noetic-on-noble" -q
# container id を確認
docker cp <container id>:/tmp/deb <target dir>

# one liner
docker cp "$(docker ps -f "ancestor=noetic-on-noble" -q):/tmp/deb" deb
```

## 参考

- ROS公式
  - <https://github.com/ros-infrastructure/ros_buildfarm>
  - <https://github.com/ros-infrastructure/ros_buildfarm_config/tree/production>
  - <https://github.com/ros/rosdistro/tree/master/noetic>
  - <https://github.com/ros/metapackages/tree/noetic-devel>
- その他
  - <https://github.com/lucasw/ros_from_src>
