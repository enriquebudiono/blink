import asyncio
import json

from aiohttp import ClientSession
from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth

import scrypted_sdk
from scrypted_sdk import (
    ScryptedDeviceBase,
    DeviceProvider,
    Settings,
    Setting,
    ScryptedInterface,
    ScryptedDeviceType,
    Device,
)

from .camera import BlinkCamera


class BlinkProvider(ScryptedDeviceBase, DeviceProvider, Settings):
    blink: Blink
    devices: dict[str, BlinkCamera] = {}

    def __init__(self, nativeId: str = None) -> None:
        super().__init__(nativeId=nativeId)
        asyncio.create_task(self.start_init())

    def print(self, *args, **kwargs) -> None:
        """Overrides the print() from ScryptedDeviceBase to avoid double-printing in the main plugin console."""
        print(*args, **kwargs)

    @property
    def username(self) -> str:
        return self.storage.getItem("username")
    @username.setter
    def username(self, value: str):
        self.storage.setItem("username", value)

    @property
    def password(self) -> str:
        return self.storage.getItem("password")
    @password.setter
    def password(self, value: str):
        self.storage.setItem("password", value)

    @property
    def auth_data(self) -> dict:
        data = self.storage.getItem("auth_data")
        try:
            if data:
                return json.loads(data)
        except json.JSONDecodeError:
            pass
        return None
    @auth_data.setter
    def auth_data(self, value: dict):
        self.storage.setItem("auth_data", json.dumps(value))

    async def getSettings(self) -> list[Setting]:
        return [
            {
                "title": "Blink Username",
                "key": "username",
                "value": self.username,
            },
            {
                "title": "Blink Password",
                "key": "password",
                "value": self.password,
                "type": "password",
            },
            {
                "title": "2FA Code",
                "key": "2fa",
                "value": "",
            }
        ]

    async def putSetting(self, key: str, value: str) -> None:
        if key == "username":
            self.username = value
        elif key == "password":
            self.password = value
        elif key == "2fa":
            await self.finish_init(value)
        else:
            raise ValueError(f"Unknown setting key: {key}")

        if not self.auth_data:
            await self.start_init()

        await self.onDeviceEvent(ScryptedInterface.Settings.value, None)

    async def start_init(self) -> None:
        try:
            if not self.username or not self.password:
                raise Exception("Blink username and password must be set before initializing.")

            blink = Blink(session=ClientSession())
            if self.auth_data:
                auth = Auth(self.auth_data)
                waiting_for_2fa = False
            else:
                auth = Auth({"username": self.username, "password": self.password}, no_prompt=True)
                waiting_for_2fa = True
            blink.auth = auth

            started = await blink.start()
            if not started:
                raise Exception("Failed to start Blink client. Check your username and password.")

            self.auth_data = blink.auth.login_attributes
            self.blink = blink

            if not waiting_for_2fa:
                await self.finish_init("")
        except Exception as e:
            self.print(f"Error initializing Blink: {e}")
            self.blink = None
            self.auth_data = None
            raise

    async def finish_init(self, mfa_code: str) -> None:
        if mfa_code:
            await self.blink.auth.send_auth_key(self.blink, mfa_code)
            await self.blink.setup_post_verify()

        devices = []
        for key, camera in self.blink.cameras.items():
            manifest: Device = {
                "name": camera.name,
                "nativeId": camera.camera_id,
                "info": {
                    "manufacturer": "Blink",
                    "model": camera.product_type,
                    "firmware": camera.version,
                    "serialNumber": camera.serial,
                },
                "type": ScryptedDeviceType.Camera.value,
                "interfaces": [
                    ScryptedInterface.Camera.value,
                    ScryptedInterface.VideoCamera.value,
                    ScryptedInterface.MotionSensor.value,
                ],
            }
            devices.append(manifest)
            self.devices[camera.camera_id] = key  # Placeholder for BlinkCamera instance

        await scrypted_sdk.deviceManager.onDevicesChanged({
            "devices": devices
        })

    async def getDevice(self, nativeId: str) -> ScryptedDeviceBase:
        if nativeId not in self.devices:
            raise ValueError(f"Camera with nativeId {nativeId} not found.")

        if isinstance(self.devices[nativeId], BlinkCamera):
            return self.devices[nativeId]

        key = self.devices[nativeId]
        camera = self.blink.cameras[key]

        blink_camera = BlinkCamera(nativeId=nativeId, blink=self.blink, camera=camera)
        self.devices[nativeId] = blink_camera
        return blink_camera