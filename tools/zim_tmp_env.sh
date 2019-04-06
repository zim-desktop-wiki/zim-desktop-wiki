#!/bin/sh

# Run zim.py but with a temporary environment
# allows testing startup without config files

export TMPDIR="/tmp/zim-tmp-env"

echo "Setting up environment in:" $TMPDIR

rm -fr $TMPDIR
mkdir $TMPDIR

mkdir $TMPDIR/home

export HOME=$TMPDIR/home
export XDG_DATA_HOME=$TMPDIR/xdg_data_home
#export XDG_DATA_DIRS=$TMPDIR/xdg_data_dir
export XDG_CONFIG_HOME=$TMPDIR/xdg_config_home
export XDG_CONFIG_DIRS=$TMPDIR/xdg_config_dir
export XDG_CACHE_HOME=$TMPDIR/xdg_cache_home

./zim.py $@
