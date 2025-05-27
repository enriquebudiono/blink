import asyncio
from datetime import datetime

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

    last_image: bytes = None
    last_image_timestamp: datetime = None

    def __init__(self, nativeId: str, blink: Blink, camera: BlinkPyCamera) -> None:
        super().__init__(nativeId=nativeId)
        self.blink = blink
        self.camera = camera

    async def getPictureOptions(self) -> ResponsePictureOptions:
        return []

    async def takePicture(self, options: RequestPictureOptions = None) -> MediaObject:
        if self.last_image and self.last_image_timestamp:
            # If the last image is recent, return it instead of taking a new picture.
            if (datetime.now() - self.last_image_timestamp).total_seconds() < 60:
                return await scrypted_sdk.mediaManager.createMediaObject(self.last_image, mimeType='image/jpeg')
        await self.camera.snap_picture()
        response = await self.camera.get_media()
        picture = await response.read()
        self.last_image = picture
        self.last_image_timestamp = datetime.now()
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