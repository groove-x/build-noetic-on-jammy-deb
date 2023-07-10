# build-noetic-on-jammy-deb

Ubuntu 22.04 (Jammy Jellyfish) 用の [ROS 1 Noetic Ninjemys](http://wiki.ros.org/noetic) の binary debian package を生成するためのツール

## 基本的な動作

- ビルド環境生成
- ROS Deb Package ビルドに必要なPython Tools の生成
- Target に関連する依存パッケージのビルド
- Target のパッケージのビルド

## Jammy対応のために修正した点など

- catkin
  - オプションを変更してsetup.bash等が生成されるようにしている
- c++17指定
  - c++11 等の指定になっている部分を c++17 に変更している
  - shared_mutex, shared_lock を使用するため
    - なぜかfocalではc++11指定でも使えたようである
- hddtempの依存削除
  - diagnostic_common_diagnostics で run_depend に指定されているが jammy の標準では無いので、依存を削除してビルドしている
- arm64 は ros-desktop のビルドが可能
  - gazebo 系のパッケージが無いので ros-desktop-full がビルドできない
- amd64 は ros-desktop-full のビルドが可能

## ビルド手順

```bash
# ビルド環境の生成 arm64 では desktop_full はビルドできない
make desktop # or desktop_full or ros_base
# ビルド環境と構築とログイン
make login

# ログイン後
# すべてビルド
make

# debパッケージは /tmp/deb 以下にできます

# 以下は一部をビルドするための手順
# ビルド用ツールの作成
make python_tools

# 特定のパッケージと、それに必要なパッケージ
# 例: std_msgs
make std_msgs
```

## ファイルの取り出し手順

ビルド後の docker を落とさずに下記を別シェルで実行

```bash
# /tmp に deb ファイルが生成されるので、それを取り出す
docker ps -f "ancestor=noetic-on-jammy" -q
# container id を確認
docker cp <container id>:/tmp/deb <target dir>

# one liner
docker cp "$(docker ps -f "ancestor=noetic-on-jammy" -q):/tmp/deb" deb
```

## 参考

- ROS公式
  - <https://github.com/ros-infrastructure/ros_buildfarm>
  - <https://github.com/ros-infrastructure/ros_buildfarm_config/tree/production>
  - <https://github.com/ros/rosdistro/tree/master/noetic>
  - <https://github.com/ros/metapackages/tree/noetic-devel>
- その他
  - <https://github.com/lucasw/ros_from_src>
