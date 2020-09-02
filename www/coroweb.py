import asyncio, os, inspect, logging, functools

from urllib import parse

from aiohttp import web

# from apis import APIError

# @get和@post
def get(path):
    '''
    Define decorator @get('/path')
    '''
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args,**kw):
            return func(*args,**kw)
        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper
    return decorator

# 定义RequestHandler
class RequestHandler(object):

    def __init__(self,app,fn):
        self._app = app
        self._func = fn
        ...

    @asyncio.coroutine
    def __call__(self,request):
        # kw = ...获取参数
        r = yield from self._func(**kw)
        return r

def add_route(app,fn):
    method = getattr(fn, '__method__', None)
    path = getattr(fn, '__route__', None)
    if path is None or method is None:
        raise ValueError('@get or @post not defined in %s.' % str(fn))
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn)
    logging.info('add route %s %s => %s(%s)' % (method, path, fn.__name__, ','.join(inspect.signature(fn).parameters.keys())))
    app.router.add_route(method, path, RequestHandler(app,fn))

def add_routes(app,module_name):
    n = module_name.rfind(',')
    if n==(-1):
        mod = __import__(module_name,globals(),locals())
    else:
        name = module_name[n+1:]
        mod = getattr(__import__(module_name[:n],globals,locals(),[name]),name)
    for attr in dir(mod):
        if attr.startswith('_'):
            continue
        fn = getattr(mod,attr)
        if callable(fn):
            method = getattr(fn,'__method__',None)
            path = getattr(fn,'__route__',None)
            if method and path:
                add_route(app,fn)

#  middleware ,middleware的用处就在于把通用的功能从每个URL处理函数中拿出来，集中放到一个地方。
#  例如，一个记录URL日志的logger可以简单定义如下：
@asyncio.coroutine
def logger_factory(app,handler):
    @asyncio.coroutine
    def logger(request):
        # 记录日志
        logging.info('Request: %s %s' % (request.method, request.path))
        # 继续处理请求
        return (yield from handler(request))
    return logger

#  而response这个middleware把返回值转换为web.Response对象再返回，以保证满足aiohttp的要求：
@asyncio.coroutine
def response_factory(app,handler):
    @asyncio.coroutine
    def response(request):
        # 结果
        r = yield from handler(request)
        if isinstance(r, web.StreamResponse):
            return r
        if isinstance(r,bytes):
            resp = web.Response(body=r)
            resp.content_type = 'application/octet-stream'
            return resp
        if isinstance(r,str):
            resp = web.Response(body=r.encode('utf-8'))
            resp.content_type = 'text/html:charset=utf-8'
            return resp
        # if isinstance(r,dict):
        #     ...

#  有了这些基础设施，我们就可以专注地往handlers模块不断添加URL处理函数了，可以极大地提高开发效率。