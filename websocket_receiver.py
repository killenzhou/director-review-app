# -*- coding: utf-8 -*-
# --- START OF FILE websocket_receiver.py ---

import asyncio
import websockets
import threading

class WebSocketReceiver:
    def __init__(self, host, port, on_message_callback, on_connect_callback=None):
        self.host = host
        self.port = port
        self.on_message_callback = on_message_callback
        self.on_connect_callback = on_connect_callback
        self.server_thread = None
        self.loop = None
        self.server = None
        self.stop_future = None

    async def _handler(self, websocket):
        if self.on_connect_callback and self.loop:
            self.loop.call_soon_threadsafe(self.on_connect_callback)
        try:
            async for message in websocket:
                if self.on_message_callback and self.loop:
                    self.loop.call_soon_threadsafe(self.on_message_callback, message)
        except websockets.exceptions.ConnectionClosed:
            print(f"客户端断开连接: {websocket.remote_address}")
        except Exception as e:
            print(f"WebSocket处理程序错误: {e}")

    async def _main_server_logic(self):
        try:
            self.stop_future = self.loop.create_future()
            async with websockets.serve(self._handler, self.host, self.port) as server:
                self.server = server
                print(f"WebSocket服务器正在监听 ws://{self.host}:{self.port}")
                await self.stop_future
        except OSError as e:
             if e.errno == 10048: print(f"错误: 端口 {self.port} 已被占用。")
             else: print(f"WebSocket服务器OS错误: {e}")
        finally:
            print("WebSocket服务器已关闭。")

    def _run_server_loop(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self._main_server_logic())
        except Exception as e:
            print(f"WebSocket服务器线程错误: {e}")
        finally:
            if self.loop.is_running(): self.loop.stop()
            self.loop.close()
            print("WebSocket服务器线程循环结束。")
            
    def start_server(self):
        if self.server_thread and self.server_thread.is_alive(): return
        self.server_thread = threading.Thread(target=self._run_server_loop, daemon=True)
        self.server_thread.start()

    def stop_server(self):
        if not self.loop or not self.server or not self.server_thread.is_alive(): return
        print("正在停止WebSocket服务器...")
        
        # This is the thread-safe way to stop the server.
        # It schedules the close coroutine to be run on the server's own event loop.
        if self.stop_future and not self.stop_future.done():
            self.loop.call_soon_threadsafe(self.stop_future.set_result, True)

        self.server_thread.join(timeout=2)
        if self.server_thread.is_alive():
            print("服务器线程未能优雅地停止。")
        
        self.server_thread = None
        self.loop = None
        self.server = None
