import asyncio
import glob
import shutil
import traceback
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi import BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

from pydantic import BaseModel

import uuid
from asyncio import Lock
import urllib.parse
import os
import logging
class VocalRemovalRequest(BaseModel):
    youtube_url: str

class StatusCheck(BaseModel):
    request_id: str


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static" )
REQUEST_STATIC_DIR = os.path.join(STATIC_DIR, "by_request_id" )
os.makedirs(REQUEST_STATIC_DIR, exist_ok=True)

TASK_STATUS_LOCK = Lock()
VOCAL_REMOVER_PATH=os.getenv("VOCAL_REMOVER_PATH")
TEMP_DIR = os.getenv('TEMP_DIR')
YOUTUBE_DL_FFMPEG_PATH=os.getenv('YOUTUBE_DL_FFMPEG_PATH')
MAX_REQUESTS_PER_HOUR=2

if not VOCAL_REMOVER_PATH:
    raise ValueError("VOCAL_REMOVER_PATH environment variable not set")
if not os.path.exists(VOCAL_REMOVER_PATH):
    raise ValueError(f"VOCAL_REMOVER_PATH {VOCAL_REMOVER_PATH} does not exist")

if not TEMP_DIR:
    raise ValueError("TEMP_DIR environment variable not set")
if not os.path.exists(TEMP_DIR):
    raise ValueError(f"TEMP_DIR {TEMP_DIR} does not exist")

if not YOUTUBE_DL_FFMPEG_PATH:
    raise ValueError("YOUTUBE_DL_FFMPEG_PATH environment variable not set")
if not os.path.exists(YOUTUBE_DL_FFMPEG_PATH):
    raise ValueError(f"YOUTUBE_DL_FFMPEG_PATH {YOUTUBE_DL_FFMPEG_PATH} does not exist")

# Dictionary to keep track of tasks and their statuses
TASK_STATUSES = {}


app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))



@app.post("/remove-vocals")
async def remove_vocals(request: VocalRemovalRequest, background_tasks: BackgroundTasks):
    async with TASK_STATUS_LOCK:
        if len(TASK_STATUSES) >= MAX_REQUESTS_PER_HOUR:
            return {"error": "Maximum number of requests per hour reached. Please try again later."}

    request_id = str(uuid.uuid4())

    async with TASK_STATUS_LOCK:
        TASK_STATUSES[request_id] = {"status": "pending", "progress": "Queuing your request", "output_path": None, "error_message": None}
    background_tasks.add_task(process_vocal_removal, request_id, request.youtube_url)
    return {"request_id": request_id}


async def run_subprocess_command(request_id,cmd,cmd_description,**kwargs):
    stdout =[]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        **kwargs
    )

    while True:
        line = await process.stdout.readline()
        if not line:
            break
        line = line.decode().strip()
        stdout.append(line)
        async with TASK_STATUS_LOCK:
            TASK_STATUSES[request_id]["progress"] = f"{cmd_description}: {line}"
        logger.debug(f"{cmd_description}: {line}")

    await process.wait()
    stderr_output = 'Unable to get stderr'
    try:
        stderr_output = await process.stderr.read().decode().strip()
    except:
        pass
    stdout_output = "\n".join(stdout)
    if process.returncode == 0:
        async with TASK_STATUS_LOCK:
            TASK_STATUSES[request_id]["progress"] = f"{cmd_description} has completed"
    else:
        async with TASK_STATUS_LOCK:
            error_message  = stderr_output
            if error_message=='Unable to get stderr':
                error_message = stdout_output
            TASK_STATUSES[request_id] = {"status": "error", "error_message": f"Error when {cmd_description}. {error_message}"}

    return stdout_output,stderr_output

async def download_youtube_video(request_id: str, youtube_url: str,working_dir:str):
    # Construct the command to run youtube-dl as a subprocess
    cmd = [
        "youtube-dl",
        "--extract-audio",
        "--output", f"{working_dir}/%(title)s.%(ext)s",
        "--add-metadata",
        "--embed-thumbnail",
        "--newline",
        "--ffmpeg-location",YOUTUBE_DL_FFMPEG_PATH,
        youtube_url
    ]


    return await run_subprocess_command(request_id,cmd,"downloading the youtube video")


async def convert_to_wav(request_id: str, working_dir: str,input_file:str):
    cmd = [
        os.path.join(YOUTUBE_DL_FFMPEG_PATH,"ffmpeg"),
        "-i", input_file,
        "-ar", "16000",
        "-ac", "1",
        "-c", "pcm_s16le",
        f"{working_dir}/{os.path.splitext(os.path.basename(input_file))[0]}.wav"
    ]
    return await run_subprocess_command(request_id,cmd,"converting to wav")

async def run_vocal_removal(request_id: str, working_dir: str,input_file:str):
    cmd = [
        "python",
        f"{VOCAL_REMOVER_PATH}/inference.py",
        "--input", input_file,
        "--output_dir", working_dir,
        "--tta"
    ]
    
    return await run_subprocess_command(request_id, cmd, "running the vocal removal process", cwd=VOCAL_REMOVER_PATH)

async def get_youtube_id(request_id: str,youtube_url: str):
    cmd = [
        "youtube-dl",
        "--get-id",
        youtube_url
    ]
    youtube_id, stderr = await run_subprocess_command(request_id, cmd, "getting YouTube video ID")
    return youtube_id.strip()

async def process_vocal_removal(request_id: str, youtube_url: str):

    async def delayed_remove_task_from_statuses():
        await asyncio.sleep(3600)  # 60 minutes in seconds
        async with TASK_STATUS_LOCK:
            if request_id in TASK_STATUSES:
                del TASK_STATUSES[request_id]

    # we use this to throttle total number of requests per hour, this is meant as a small hobby server. Shouldn't be used for mass requests.
    # there is a corresponding check in the /remove-vocals endpoint to limit the number of requests per hour
    asyncio.create_task(delayed_remove_task_from_statuses())

    try:
        youtube_id = await get_youtube_id(request_id,youtube_url)

        async with TASK_STATUS_LOCK:
            if TASK_STATUSES[request_id]["status"] == "error":
                return
            TASK_STATUSES[request_id]["youtube_id"] = youtube_id

        working_dir = os.path.abspath(os.path.join(TEMP_DIR, youtube_id))
        youtube_temp_dir = os.path.abspath(os.path.join(working_dir, "youtube"))
        vocal_remover_temp_dir = os.path.abspath(os.path.join(working_dir, "vocal-remover"))
        ffmpeg_temp_dir = os.path.abspath(os.path.join(working_dir, "ffmpeg"))

        # Create directories for processing
        os.makedirs(youtube_temp_dir, exist_ok=True)
        os.makedirs(vocal_remover_temp_dir, exist_ok=True)
        os.makedirs(ffmpeg_temp_dir, exist_ok=True)

        audio_files_pre_check = glob.glob(f"{youtube_temp_dir}/*.wav")
        if audio_files_pre_check:
            logger.info(f"Audio file already exists under {youtube_temp_dir}. Skipping download.")
        else:
            await download_youtube_video(request_id,youtube_url,youtube_temp_dir)
            async with TASK_STATUS_LOCK:
                if TASK_STATUSES[request_id]["status"] == "error":
                    return

        audio_files = glob.glob(f"{youtube_temp_dir}/*.*")
        if not audio_files:
            async with TASK_STATUS_LOCK:
                TASK_STATUSES[request_id] = {"status": "error", "error_message": "No audio file found after downloading the YouTube video"}
            return
        
        if len(audio_files)>1:
            async with TASK_STATUS_LOCK:
                TASK_STATUSES[request_id] = {"status": "error", "error_message": f"Multiple files found after youtube download. Please ensure only one audio file is present. Files: {', '.join(audio_files)}"}
            return



        ffmpeg_input_file = audio_files[0]

        if ffmpeg_input_file.endswith(".wav"):
            logger.info(f"Input file is already in WAV format. Using it directly for vocal removal.")
            vocal_remover_input_file = ffmpeg_input_file
        else:
            converted_check = glob.glob(f"{ffmpeg_temp_dir}/*.wav")
            if converted_check:
                logger.info(f"Converted WAV file already exists under {ffmpeg_temp_dir}. Skipping conversion.")
                vocal_remover_input_file = converted_check[0]
            else:
                await convert_to_wav(request_id,ffmpeg_temp_dir,ffmpeg_input_file)
                converted_files = glob.glob(f"{ffmpeg_temp_dir}/*.wav")

                async with TASK_STATUS_LOCK:
                    if TASK_STATUSES[request_id]["status"] == "error":
                        return
                if not converted_files:
                    async with TASK_STATUS_LOCK:
                        TASK_STATUSES[request_id] = {"status": "error", "error_message": "Failed to convert audio file to WAV format"}
                    return
                vocal_remover_input_file = converted_files[0]


        instruments_files_check = glob.glob(f"{vocal_remover_temp_dir}/*_Instruments.wav")
        if instruments_files_check:
            logger.info(f"Instruments file already exists under {vocal_remover_temp_dir}. Skipping vocal removal.")
        else:
            stdout,stderr = await run_vocal_removal(request_id, vocal_remover_temp_dir, vocal_remover_input_file)
            logger.debug(f"stdout: {stdout}")
            logger.debug(f"stderr: {stderr}")

        async with TASK_STATUS_LOCK:
            if TASK_STATUSES[request_id]["status"] == "error":
                return
            
        instruments_file = glob.glob(f"{vocal_remover_temp_dir}/*_Instruments.wav")[0]
        output_file_name = os.path.basename(instruments_file.replace('_Instruments.wav',' Instruments.wav'))
        output_path = f"{REQUEST_STATIC_DIR}/{request_id}/{output_file_name}"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        shutil.copy(instruments_file, output_path)
        async with TASK_STATUS_LOCK:
            static_url = f"/static/by_request_id/{request_id}/{output_file_name}"
            # url encode static url:
            static_url_encoded = urllib.parse.quote(static_url)
            TASK_STATUSES[request_id].update({"status": "success", "output_path": static_url_encoded, "filename": output_file_name})

        # Delete the working directory
        
        async def delayed_directory_removal():
            await asyncio.sleep(1800)  # 30 minutes in seconds
            shutil.rmtree(working_dir)


        # keep it around for a while in case multiple requests are made at the same time
        asyncio.create_task(delayed_directory_removal())
        
    except Exception as e:
        async with TASK_STATUS_LOCK:
            traceback_str = traceback.format_exc()
            TASK_STATUSES[request_id] = {"status": "error", "error_message": f"Critical failure. Error: {traceback_str}"}

@app.get("/check-status/{request_id}")
async def check_status(request_id: str):
    async with TASK_STATUS_LOCK:
        if request_id in TASK_STATUSES:
                return TASK_STATUSES[request_id]
        else:
            raise HTTPException(status_code=404, detail="Request ID not found")



