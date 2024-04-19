source ../venv/bin/activate
mkdir -p workdir
export TEMP_DIR=workdir
export VOCAL_REMOVER_PATH=/home/shmuel/Downloads/vocal-remover/vocal-remover
export YOUTUBE_DL_FFMPEG_PATH=/home/shmuel/repos/hobby-hoster-projects/vocal-remover/ffmpeg-master-latest-linux64-gpl/bin
export PATH=`realpath ..`:$PATH
uvicorn main:app --reload
