
FROM debian:bullseye-20240408


RUN apt-get update && \
    apt-get install -y python3 python3-pip unzip wget cmake make zlib1g-dev git libgl1 libglib2.0-0 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN ln -s /usr/bin/python3 /usr/bin/python

# INSTALL VOCAL REMOVER

# install from github since it contains pretrained models embedded as an asset
ADD https://github.com/tsurumeso/vocal-remover/releases/download/v5.1.0/vocal-remover-v5.1.0.zip /vocal-remover/
RUN unzip /vocal-remover/vocal-remover-v5.1.0.zip -d /vocal-remover/ && \
    rm /vocal-remover/vocal-remover-v5.1.0.zip
# their requirements.txt does not include torch installations. So we patch it
COPY vocal-remover-patches/vocal-requirements.txt /vocal-remover/requirements.txt
RUN cd /vocal-remover/ && pip3 install -r requirements.txt
COPY vocal-remover-patches/inference_patch.py /vocal-remover/vocal-remover/inference.py
ENV VOCAL_REMOVER_PATH="/vocal-remover/vocal-remover"


# INSTALL YOUTUBE-DL

# not using pip install since pypi hasn't been updated in three years. Use the latest nightly build as of the time of writing
ADD https://github.com/ytdl-org/ytdl-nightly/releases/download/2024.04.08/youtube-dl /usr/local/bin/youtube-dl
RUN chmod a+rx /usr/local/bin/youtube-dl

# custom build of ffmpeg by youtube-dl, supposedly better integrated with youtube-dl
ADD https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz /youtube-dl-ffmpeg/
RUN tar -xJf /youtube-dl-ffmpeg/ffmpeg-master-latest-linux64-gpl.tar.xz -C /youtube-dl-ffmpeg/ && \
    rm /youtube-dl-ffmpeg/ffmpeg-master-latest-linux64-gpl.tar.xz && \
    mkdir -p /opt/youtube-dl-ffmpeg && \
    mv /youtube-dl-ffmpeg/ffmpeg-master-latest-linux64-gpl/* /opt/youtube-dl-ffmpeg/ && \
    rmdir /youtube-dl-ffmpeg/ffmpeg-master-latest-linux64-gpl

ENV YOUTUBE_DL_FFMPEG_PATH="/opt/youtube-dl-ffmpeg/bin"


# INSTALL ATOMIC PARSLEY

# used for embedding metadata in media by youtube-dl. We would have used the artifact on github, but it
# requires GLIBC_2.33 and we have 2.31.

RUN git clone https://github.com/wez/atomicparsley.git /atomicparsley-source && \
    cd /atomicparsley-source && \
    git checkout 171e8aeba2ca486d0a9049341ef91594683663ea && \
    cmake . && \
    cmake --build . --config Release && \
    mv /atomicparsley-source/AtomicParsley /usr/local/bin/ && \
    rm -rf /atomicparsley-source


# SETUP OUR WEB APP

RUN mkdir -p /tmp
ENV TEMP_DIR="/tmp"

COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

RUN mkdir app

COPY app app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]