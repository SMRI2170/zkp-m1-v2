"""Loopback TCP fault transport; partitions close active connections and deny reconnect."""
import asyncio
import threading

class FaultNetwork:
    def __init__(self):
        self.groups=None;self.delay=0;self.bytes=0;self.connections={};self.blocked=0
        self.loop=asyncio.new_event_loop();self.thread=threading.Thread(target=self.loop.run_forever,daemon=True)
        self.thread.start()
        asyncio.run_coroutine_threadsafe(self.start(),self.loop).result(timeout=10)
    def port(self,source,target): return 31400+source*4+target
    def allowed(self,source,target): return self.groups is None or self.groups[source]==self.groups[target]
    async def start(self):
        self.servers=[]
        for source in range(4):
            for target in range(4):
                if source!=target:
                    self.servers.append(await asyncio.start_server(lambda r,w,s=source,t=target:self.connect(r,w,s,t),'127.0.0.1',self.port(source,target)))
    async def connect(self,reader,writer,source,target):
        if not self.allowed(source,target):self.blocked+=1;writer.close();return
        backend=None;tasks=[];token=object()
        try:
            br,backend=await asyncio.open_connection('127.0.0.1',30431+target)
            self.connections[token]=(source,target,writer,backend)
            async def relay(r,w):
                while True:
                    data=await r.read(65536)
                    if not data:break
                    if not self.allowed(source,target):self.blocked+=1;break
                    if self.delay:await asyncio.sleep(self.delay)
                    self.bytes+=len(data);w.write(data);await w.drain()
            tasks=[asyncio.create_task(relay(reader,backend)),asyncio.create_task(relay(br,writer))]
            done,pending=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            for task in pending:task.cancel()
            for task in done:task.result()
        except (OSError,ConnectionError,asyncio.CancelledError):pass
        finally:
            for task in tasks:task.cancel()
            self.connections.pop(token,None);writer.close()
            if backend:backend.close()
    async def change(self,groups,delay):
        self.groups=groups;self.delay=delay
        for source,target,front,back in list(self.connections.values()):
            if not self.allowed(source,target):front.close();back.close()
    def configure(self,groups=None,delay=0):
        asyncio.run_coroutine_threadsafe(self.change(groups,delay),self.loop).result(timeout=5)
    async def shutdown(self):
        for server in self.servers:server.close();await server.wait_closed()
        for _,_,front,back in list(self.connections.values()):front.close();back.close()
        await asyncio.sleep(.1)
    def close(self):
        asyncio.run_coroutine_threadsafe(self.shutdown(),self.loop).result(timeout=5)
        self.loop.call_soon_threadsafe(self.loop.stop);self.thread.join(timeout=5)
