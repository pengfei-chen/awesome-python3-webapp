import logging; logging.basicConfig(level=logging.INFO)

import asyncio, os, json, time
from datetime import datetime
from models import User
from coroweb import get
import orm,coroweb

from aiohttp import web

# def index(request):
#     return web.Response(body=b'<h1>Awesome</h1>',content_type='text/html')

@get('/')
@asyncio.coroutine
def index(request):
    users = yield from User.findAll()
    return {
      '__template__':'test.html',
      'users':users
    }

@asyncio.coroutine
def init(loop):
    app = web.Application(loop=loop)
    app.router.add_route('GET', '/', index)
    srv = yield from loop.create_server(app.make_handler(), '127.0.0.1', 9000)
    logging.info('server started at http://127.0.0.1:9000...')
    return srv


loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()

def datetime_filter(t):
    delta = int(time.time() - t)
    if delta < 60:
        return u'1分钟前'
    if delta < 3600:
        return u'%s分钟前' % (delta // 60)
    if delta < 86400:
        return u'%s小时前' % (delta // 3600)
    if delta < 604800:
        return u'%s天前' % (delta // 86400)
    dt = datetime.fromtimestamp(t)
    return u'%s年%s月%s日' % (dt.year, dt.month, dt.day)


# app = web.Application(loop=loop, middlewares=[logger_factory,response_factory])
# init_jinja2(app,filters=dict(datetime=datetime_filter))
# add_routes(app,'handlers')
# add_static(app)
