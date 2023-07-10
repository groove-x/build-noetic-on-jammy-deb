.PHONY: run
run: desktop

# all: venv gen_build_env.py
# 	$(VENV)/python gen_build_env.py --all

# all-arm64: venv gen_build_env.py
# 	$(VENV)/python gen_build_env.py --all --ignore gazebo

ros_base: venv gen_build_env.py
	$(VENV)/python gen_build_env.py --targets ros_base

desktop: venv gen_build_env.py
	$(VENV)/python gen_build_env.py --targets desktop

desktop_full: venv gen_build_env.py
	$(VENV)/python gen_build_env.py --targets desktop_full

# arm64 ubuntu does not have packages of gazebo and libgazebo-dev.
desktop_full_arm64: venv gen_build_env.py
	$(VENV)/python gen_build_env.py --targets desktop perception stage_ros

docker/build_ros_package.sh: build_ros_package.sh
	rm -f $@
	cp $< $@

docker/.image: docker/Dockerfile docker/build_ros_package.sh docker/Makefile
	# docker build --platform linux/x86_64 -t noetic-on-jammy docker
	docker build -t noetic-on-jammy docker
	touch docker/.image

login: docker/.image
	# docker run --platform linux/x86_64 -it --rm  noetic-on-jammy bash
	docker run -it --rm  noetic-on-jammy bash

.PHONY: clean clean-cache clean-all
clean:
	rm -rf docker

clean-cache:
	rm -rf cache

clean-all: clean clean-cache clean-venv

# https://github.com/sio/Makefile.venv
include Makefile.venv
Makefile.venv:
	curl \
		-o Makefile.fetched \
		-L "https://github.com/sio/Makefile.venv/raw/v2023.04.17/Makefile.venv"
	echo "fb48375ed1fd19e41e0cdcf51a4a0c6d1010dfe03b672ffc4c26a91878544f82 *Makefile.fetched" \
		| sha256sum --check - \
		&& mv Makefile.fetched Makefile.venv
