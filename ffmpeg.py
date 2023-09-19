from pathlib import Path

import torch
import subprocess
import shlex
import math
import platform
from termcolor import colored

try:
    from pyadl import *
except Exception as ex:
    pass


def getGPUtype():
    try:
        adv = ADLManager.getInstance().getDevices()
        ac = []
        for a in adv:
            ab = [str(a.adapterIndex), str(a.adapterName)]
            ac.append(ab)
    except:
        ac = None
    return ac


class FFMPEG_recorder:
    """Hardware Acceleration for video recording using FFMPEG
    Documents: https://trac.ffmpeg.org/wiki/Encode/H.265
    """
    video_codecs = ["hevc_nvenc", "hevc_amf", "hevc_vaapi", "libx264"]

    def __init__(self, save_path=None, videoDimensions=(1280, 720), fps=30, bitRate=0, vcode=""):
        """_FFMPEG recorder_
        Args:
            save_path (__str__, optional): _description_. Defaults to None.
            videoDimensions (tuple, optional): _description_. Defaults to (1280, 720).
            fps (int, optional): _description_. Defaults to 30
        """
        self.codec = None
        self.dimension = videoDimensions
        self.fps = fps
        os_type = platform.uname().system
        if vcode == "":
            if torch.cuda.is_available():
                self.codec = 'hevc_nvenc'
            elif os_type == 'Windows' and 'AMD' in str(getGPUtype()):
                self.codec = 'hevc_amf'
            elif os_type == 'Linux' and 'AMD' in str(getGPUtype()):
                self.codec = 'hevc_vaapi'
            else:
                self.codec = 'libx264'
        else:
            if vcode in self.video_codecs:
                self.codec = vcode
            else:
                self.codec = self.video_codecs[-1]

        print(f'Using video codec: {self.codec}, os: {os_type}, height: {videoDimensions[1]}, '
              f'width: {videoDimensions[0]}, fps: {fps}.')
        if bitRate == 0:
            mpx = math.prod(self.dimension)
            self.bitRate = round(
                20 * (mpx / (3840 * 2160)) * (1 if round(self.fps / 30, 3) < 1 else round(self.fps / 30, 3)), 3)
        else:
            self.bitRate = bitRate

        self.save_path = save_path
        self.countFrame = 0
        self.startTime = 0.

        self.subtitleContent = ''

        cmd = ['ffmpeg', '-v', 'quiet', '-y', '-s', f'{self.dimension[0]}x{self.dimension[1]}',
               '-pixel_format', 'bgr24', '-f', 'rawvideo', '-r', f'{self.fps}', '-i', 'pipe:', '-vcodec',
               f'{self.codec}', '-pix_fmt', 'yuv420p', '-b:v', f'{self.bitRate}M', f'"{save_path}"']
        cmd_str = ""
        for x in cmd:
            cmd_str += f"{x} "
        cmd_str = cmd_str[:-1]
        self.process = subprocess.Popen(cmd_str, stdin=subprocess.PIPE)

    def writeFrame(self, image=None):
        """Write frame by frame to video

        Args:
            image (_image_, require): ndarray uint8 HWC
        """

        self.process.stdin.write(image.tobytes())

    @staticmethod
    def second_to_timecode(x=0.) -> str:
        hour, x = divmod(x, 3600)
        minute, x = divmod(x, 60)
        second, x = divmod(x, 1)
        millisecond = int(x * 1000.)
        return '%.2d:%.2d:%.2d,%.3d' % (hour, minute, second, millisecond)

    def writeSubtitle(self, title='', fps=30):
        """write subtitle string frame by frame

        Args:
            title (str, optional): _description_. Defaults to ''.
            fps (int, optional): _description_. Defaults to 30.
        """
        timeStep = 1 / fps
        timecode = self.second_to_timecode(self.startTime)
        timecode2 = self.second_to_timecode(self.startTime + timeStep)
        self.startTime += timeStep

        if title == '':
            title = f'UTC2'
        frame = f'{self.countFrame}\n'
        timeStamp = f'{timecode} --> {timecode2}\n'
        sub_title = f'{title}\n'
        self.subtitleContent += f'{frame}{timeStamp}{sub_title}\n'
        self.countFrame += 1

    def addSubtitle(self, hardSubtitle=False):
        save = self.save_path.replace('.mp4', 'with_sub.mp4')
        save = f"""{save}"""
        sub_file = save.replace('.mp4', '.srt')
        with open(sub_file, 'w') as f:
            f.write(self.subtitleContent)
        self.save_path = f"""{self.save_path}"""
        if hardSubtitle:
            process = subprocess.run(
                f"ffmpeg -v quiet -i {self.save_path} -c:v copy -vf subtitles='{sub_file}' {save}")  # error for now
        else:
            process = subprocess.run(
                f"ffmpeg -v quiet -i {self.save_path} -i {sub_file} -c:v copy -c:s mov_text -metadata:s:s:0 language=eng {save}")
        return process

    def addAudio(self, audio_src):
        """
        audio_src: str | Path

        """

        if isinstance(audio_src, str):
            audio_src = Path(audio_src)
        if audio_src.is_file():
            save_dir = self.save_path.replace(".mp4", "_audio.mp4")
            cmd = ["ffmpeg", "-v", "quiet", "-i", f"{self.save_path}", "-i", f"{audio_src.as_posix()}",
                   "-c:v", "copy", "-map", "0:v",
                   "-map", "1:a?", "-y", f"{save_dir}"]
            cmd_str = ""
            for x in cmd:
                cmd_str += f"{x} "
            cmd_str = cmd_str[:-1]
            subprocess.run(cmd_str)
            return 1
        else:
            return 0

    def stopRecorder(self):
        """Stop record video"""
        self.process.stdin.close()
        self.process.terminate()
        self.process.wait()
