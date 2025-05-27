import asyncio

from blinkpy.blinkpy import Blink
from blinkpy.camera import BlinkCamera as BlinkPyCamera

import scrypted_sdk
from scrypted_sdk import (
    ScryptedDeviceBase,
    Camera,
    VideoCamera,
    MediaObject,
    ResponsePictureOptions,
    RequestPictureOptions,
    RequestMediaStreamOptions,
    ResponseMediaStreamOptions,
    FFmpegInput,
)


class BlinkCamera(ScryptedDeviceBase, Camera, VideoCamera):
    blink: Blink
    camera: BlinkPyCamera

    def __init__(self, nativeId: str, blink: Blink, camera: BlinkPyCamera) -> None:
        super().__init__(nativeId=nativeId)
        self.blink = blink
        self.camera = camera

    async def getPictureOptions(self) -> ResponsePictureOptions:
        return []

    async def takePicture(self, options: RequestPictureOptions = None) -> MediaObject:
        await self.camera.snap_picture()
        response = await self.camera.get_media()
        picture = await response.read()
        return await scrypted_sdk.mediaManager.createMediaObject(picture, mimeType='image/jpeg')

    async def getVideoStreamOptions(self) -> list[ResponseMediaStreamOptions]:
        return [
            {
                "id": "default",
                "name": "Cloud Video Stream",
                #"audio": {
                #    "codec": "aac",
                #},
                "audio": None,
                "video": {
                    "codec": "h264",
                },
                "source": "cloud",
                "tool": "ffmpeg",
                "userConfigurable": False,
            }
        ]

    async def getVideoStream(self, options: RequestMediaStreamOptions = None) -> MediaObject:
        msos = await self.getVideoStreamOptions()
        msos = msos[0]
        try:
            stream = await self.camera.init_livestream()
            await stream.start()
            asyncio.create_task(stream.feed())
            msos["container"] = "mpegts"
            url = stream.url
        except Exception as e:
            url = await self.camera.get_liveview()
            msos["container"] = "rtsp"

        ffmpeg_input: FFmpegInput = {
            "url": url,
            "inputArguments": [
                "-i", url,
            ],
            "mediaStreamOptions": msos,
        }
        return await scrypted_sdk.mediaManager.createFFmpegMediaObject(ffmpeg_input)