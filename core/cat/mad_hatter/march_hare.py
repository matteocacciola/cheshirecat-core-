import os
import hashlib
import shutil
import redis
import time
from datetime import datetime
from typing import Dict, List, Final
import threading
from dateutil.tz import UTC

from cat import utils
from cat.bill_the_lizard import BillTheLizard
from cat.env import get_env
from cat.factory.custom_filemanager import BaseFileManager
from cat.log import log
from cat.mad_hatter.tweedledum import Tweedledum
from cat.utils import singleton


@singleton
class MarchHare:
    def __init__(self):
        """
        Initialize the distributed handler of plugins il
        """
        lizard = BillTheLizard()

        self.__file_manager: Final[BaseFileManager] = lizard.plugin_filemanager
        self.__plugin_manager: Final[Tweedledum] = lizard.plugin_manager

        self.__redis_client: Final[redis.Redis] = self.__get_redis_client()
        self.__plugin_dir: Final[str] = utils.get_plugins_path()

        self.__last_sync = None

        # Key to track last modify timestamp
        self.__last_update_key: Final[str] = "plugins:last_update"
        # Key to track sync lock
        self.__sync_lock_key: Final[str] = "plugins:sync_lock"

    def __get_redis_client(self) -> redis.Redis:
        password = get_env("CCAT_REDIS_PASSWORD")

        main_db = get_env("CCAT_REDIS_DB")
        this_db = "2"
        if main_db != "0":
            this_db = "0"

        if password:
            return redis.Redis(
                host=get_env("CCAT_REDIS_HOST"),
                port=int(get_env("CCAT_REDIS_PORT")),
                db=this_db,
                password=password,
                encoding="utf-8",
                decode_responses=True
            )

        return redis.Redis(
            host=get_env("CCAT_REDIS_HOST"),
            port=int(get_env("CCAT_REDIS_PORT")),
            db=this_db,
            encoding="utf-8",
            decode_responses=True
        )

    def __calculate_checksum(self, file_path: str) -> str:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def __acquire_lock(self, timeout=10) -> bool:
        """
        Acquire a distributed lock with timeout

        Args:
            timeout: Timeout in seconds

        Returns:
            bool: True if lock is acquired
        """

        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.__redis_client.set(self.__sync_lock_key, "1", nx=True, ex=30):
                return True
            time.sleep(0.1)
        return False

    def __release_lock(self):
        self.__redis_client.delete(self.__sync_lock_key)

    def __update_last_modified(self):
        self.__redis_client.set(self.__last_update_key, datetime.utcnow().isoformat())

    def __get_plugin_info(self, plugin_name: str) -> Dict | None:
        """
        Get the information on a specific plugin

        Args:
            plugin_name: Name of the plugin

        Returns:
            Dict | None: Information about the plugin, or None if not found
        """

        info = self.__redis_client.hgetall(f"plugin:{plugin_name}")
        return info if info else None

    def list_plugins(self) -> List[Dict]:
        """
        List all the installed plugins, with their information

        Returns:
            List[Dict]: List of information about the plugins
        """
        plugins = []
        plugin_keys = self.__redis_client.keys("plugin:*")

        for key in plugin_keys:
            plugin_info = self.__get_plugin_info(key)
            if plugin_info:
                plugins.append(plugin_info)

        return plugins

    def upload_plugin_to_storage(self, plugin_zip_path: str) -> bool:
        """
        Upload a new plugin on the remote storage and notify the other nodes

        Args:
            plugin_zip_path: Path of the zip file of the plugin

        Returns:
            bool: True if the upload is successful
        """
        if not self.__acquire_lock():
            log.error("It is not possible to acquire the lock for installation")
            return False

        try:
            plugin_name = os.path.basename(plugin_zip_path)
            plugin_remote_path = os.path.join(self.__file_manager.storage_dir, plugin_name)
            if self.__file_manager.file_exists(plugin_remote_path):
                self.remove_plugin_from_storage(plugin_name, notify=False)

            self.__file_manager.upload_file_to_storage(plugin_zip_path)

            plugin_info = {
                "name": plugin_name,
                "checksum": self.__calculate_checksum(plugin_zip_path),
                "timestamp": datetime.now(UTC).isoformat(),
                "path": plugin_remote_path,
            }

            self.__redis_client.hset(f"plugin:{plugin_name}", mapping=plugin_info)
            self.__update_last_modified()
            self.__redis_client.publish("plugin_updates", "update")

            log.info(f"Plugin {plugin_name} successfully uploaded on remote storage")
            return True
        except Exception as e:
            log.error(f"Error during the uploading of the plugin to the remote storage: {str(e)}")
            return False
        finally:
            self.__release_lock()

    def remove_plugin_from_storage(self, plugin_name: str, notify: bool = True) -> bool:
        """
        Remove a plugin from the remote storage and notify the other nodes, if needed

        Args:
            plugin_name: Name of the plugin to uninstall
            notify: Flag to notify the other nodes

        Returns:
            bool: True if the removal is successful
        """
        if not self.__acquire_lock():
            log.error("It is not possible to acquire the lock for uninstallation")
            return False

        try:
            plugin_path = os.path.join(self.__file_manager.storage_dir, plugin_name)
            if not self.__file_manager.file_exists(plugin_path):
                log.warning(f"Plugin {plugin_name} not found")
                return False

            self.__file_manager.remove_file_from_storage(plugin_path)
            self.__redis_client.delete(f"plugin:{plugin_name}")
            self.__update_last_modified()
            if notify:
                self.__redis_client.publish("plugin_updates", "update")

            log.info(f"Plugin {plugin_name} successfully removed from the remote storage")
            return True
        except Exception as e:
            log.error(f"Error during the removal of the plugin from the remote storage: {str(e)}")
            return False
        finally:
            self.__release_lock()

    def __download_and_install_plugin(self, plugin_info: Dict, download_path: str) -> None:
        # download the plugin from the storage
        archive_path = self.__file_manager.download_file_from_storage(plugin_info["path"], download_path)
        # install the downloaded archive
        self.__plugin_manager.install_plugin(archive_path)

    def sync_plugins(self) -> None:
        try:
            remote_plugins = self.list_plugins()
            local_plugins = self.__plugin_manager.plugins.keys()

            # remove the local folders related to plugins no more existing in Redis
            for local_plugin in local_plugins:
                if not any(os.path.splitext(plugin_info["name"])[0] == local_plugin for plugin_info in remote_plugins):
                    self.__plugin_manager.uninstall_plugin(local_plugin)

            for plugin_info in remote_plugins:
                plugin_name, plugin_extension = os.path.splitext(plugin_info["name"])
                local_plugin_path = os.path.join(self.__plugin_dir, plugin_name)

                # create a temporary directory to zip/unzip the local_path_plugin and compare checksum
                tmp_path = f"/tmp/{plugin_name}"

                # the plugin exists
                if os.path.exists(local_plugin_path):
                    # create a zip file with the entire content of current local_plugin_path
                    shutil.make_archive(plugin_name, plugin_extension, tmp_path, local_plugin_path)

                    local_checksum = self.__calculate_checksum(
                        os.path.join(tmp_path, f"{plugin_name}.{plugin_extension}")
                    )

                    # check if the plugin is updated by comparing the checksum of the local plugin archive and the
                    # remote one stored within the Redis
                    if local_checksum != plugin_info["checksum"]:
                        self.__download_and_install_plugin(plugin_info, tmp_path)
                else:
                    self.__download_and_install_plugin(plugin_info, tmp_path)

                # cleanup
                if os.path.exists(tmp_path):
                    shutil.rmtree(tmp_path)

            self.__last_sync = datetime.now(UTC).isoformat()
        except Exception as e:
            log.error(f"Error during the synchronization of the plugin: {str(e)}")

    def periodic_sync(self, interval: int = 60):
        """
        Execute the periodic sync of the plugins

        Args:
            interval: Time interval, in seconds, between each sync
        """
        while True:
            if self.__check_updates_needed:
                self.sync_plugins()
            time.sleep(interval)

    def start_sync_listener(self) -> None:
        pubsub = self.__redis_client.pubsub()
        pubsub.subscribe("plugin_updates")

        for message in pubsub.listen():
            if message["type"] == "message" and message["data"] == "update":
                self.sync_plugins()

    def start(self):
        # First sync
        self.sync_plugins()

        # Start the listener in a pub/sub in un thread
        pubsub_thread = threading.Thread(
            target=self.start_sync_listener,
            daemon=True
        )
        pubsub_thread.start()

        # Start periodic sync in another thread
        sync_thread = threading.Thread(
            target=self.periodic_sync,
            daemon=True
        )
        sync_thread.start()

    @property
    def __check_updates_needed(self) -> bool:
        """
        Verify if updates are necessary

        Returns:
            bool: True if updates are needed
        """

        last_update = self.__redis_client.get(self.__last_update_key)

        if not self.__last_sync or not last_update:
            return True

        return last_update > self.__last_sync