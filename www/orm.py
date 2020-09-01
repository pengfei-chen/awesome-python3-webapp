'''
ORM简介
orm即Object Relational Mapping，全称对象关系映射。
当我们需要对数据库进行操作时，势必需要通过连接数据、调用sql语句、执行sql语句等操作，ORM将数据库中的表，字段、行与我们面向对象编程的类及其方法，属性等一一对应，即将该部分操作封装起来，程序猿不需要懂得sql语句即可完成对数据库的操作。
'''

# 创建连接池
# 
import logging; logging.basicConfig(level=logging.INFO)

import asyncio, os, json, time,aiomysql
from datetime import datetime

def log(sql, args=()):
    logging.info('SQL: %s' % sql)

@asyncio.coroutine
def create_pool(loop,**kw):
    logging.info('create database connection pool...')
    global __pool
    __pool = yield from aiomysql.create_pool(
        host=kw.get('host','localhost'),
        port=kw.get('port',3306),
        user=kw['user'],
        password=kw['password'],
        db = kw['db'],
        charset=kw.get('charset','utf8'),
        autocommit=kw.get('autocommit',True),
        maxsize=kw.get('maxsize',10),
        minsize=kw.get('minsize',1),
        loop = loop
        )

#  Select
@asyncio.coroutine
def select(sql,args,size=None):
    log(sql,args)
    global __pool
    with (yield from __pool) as conn:
        cur = yield from conn.cursor(aiomysql.DictCursor)
        yield from cur.execute(sql.replace('?','%s'),args or ())
        if size:
            rs = yield from cur.fetchmany(size)
        else:
            rs = yield from cur.fetchall()
        yield from cur.close()
        logging.info('rows returned: %s' % len(rs))
        return rs

# SQL语句的占位符是?，而MySQL的占位符是%s，select()函数在内部自动替换。注意要始终坚持使用带参数的SQL，而不是自己拼接SQL字符串，这样可以防止SQL注入攻击。

# Insert, Update, Delete
# @asyncio.coroutine
async def execute(sql,args,autocommit=True):
    log(sql)
    async with __pool.get() as conn:
        if not autocommit:
            await conn.begin()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql.replace('?', '%s'), args)
                affected = cur.rowcount
            if not autocommit:
                await conn.commit()
        except BaseException as e:
            if not autocommit:
                await conn.rollback()
            raise
        return affected

# execute()函数和select()函数所不同的是，cursor对象不返回结果集，而是通过rowcount返回结果数。

# ORM
# 


'''
# 创建实例:
user = User(id=123, name='Michael')
# 存入数据库:
user.insert()
# 查询所有User对象:
users = User.findAll()
'''

def create_args_string(num):
    L = []
    for n in range(num):
        L.append('?')
    return ', '.join(L)


class Field(object):

    def __init__(self,name,column_type,primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default

    def __str__(self):
        return '<%s,%s,%s>' % (self.__class__.__name__, self.column_type, self.name)

#  映射varchar的StringField

class StringField(Field):

    def __init__(self, name=None, primary_key=False, default=None, ddl='varchar(100'):
        super().__init__(name,ddl,primary_key,default)


#  注意到Model只是一个基类，如何将具体的子类如User的映射信息读取出来呢？答案就是通过metaclass：ModelMetaclass：
class ModelMetaClass(type):

    def __new__(cls, name, bases, attrs):
        # 排除model类本身
        if name == 'Model':
            return type.__new__(cls,name,bases,attrs)
        # 获取table名称
        tableName = attrs.get('__table__',None) or name
        logging.info('found model: %s (table:%s)' % (name, tableName))
        # 获取所有的Pield和主键名
        mappings = dict()
        fields = []
        primaryKey = None
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('  found mapping: %s ==> %s' % (k,v))
                mappings[k] = v
                if v.primary_key:
                    # 找到主键
                    if primaryKey:
                        raise RuntimeError('Duplicate primary key for field:%s' % k)
                    primaryKey = k
                else:
                    fields.append(k)
        if not primaryKey:
            raise RuntimeError('Primary key not found')

        for k in mappings.keys():
            attrs.pop(k)

        escaped_fields = list(map(lambda f:' %s ' % f, fields))
        attrs['__mappings__'] = mappings # 保存属性和列的映射关系
        attrs['__table__'] = tableName
        attrs['__primary_key__'] = primaryKey # 主键属性名
        attrs['__fields__'] = fields # 除主键外的属性名
        # 构造默认的SELECT, INSERT, UPDATE和DELETE语句:
        attrs['__select__'] = 'select `%s`, %s from `%s`' % (primaryKey, ', '.join(escaped_fields), tableName)
        attrs['__insert__'] = 'insert into `%s` (%s, `%s`) values (%s)' % (tableName, ', '.join(escaped_fields), primaryKey, create_args_string(len(escaped_fields) + 1))
        attrs['__update__'] = 'update `%s` set %s where `%s`=?' % (tableName, ', '.join(map(lambda f: '`%s`=?' % (mappings.get(f).name or f), fields)), primaryKey)
        attrs['__delete__'] = 'delete from `%s` where `%s`=?' % (tableName, primaryKey)
        return type.__new__(cls, name, bases, attrs)

# 这样，任何继承自Model的类（比如User），会自动通过ModelMetaclass扫描映射关系，并存储到自身的类属性如__table__、__mappings__中。
# 
# 定义Model
class Model(dict,metaclass=ModelMetaClass):

    def __init__(self,**kw):
        super(Model,self).__init__(**kw)

    def __getattr__(self,key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError (r" 'Model' object has no attribute '%s' " % key )

    def __setattr__(self,key,value):
        self[key] = value

    def getValue(self,key):
        return getattr(self,key,None)

    def getValueOrDefault(self,key):
        value = getattr(self,key,None)
        if value is None:
            field = self.__mappings__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for %s: %s' % (key, str(value)))
                setattr(self,key,value)
        return value

    @classmethod
    async def find(cls, pk):
        ' find object by primary key. '
        rs = await select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    async def save(self):
        args = list(map(self.getValueOrDefault, self.__fields__))
        args.append(self.getValueOrDefault(self.__primary_key__))
        rows = await execute(self.__insert__, args)
        if rows != 1:
            logging.warn('failed to insert record: affected rows: %s' % rows)
# Model从dict继承，所以具备所有dict的功能，同时又实现了特殊方法__getattr__()和__setattr__()，因此又可以像引用普通字段那样写：


# 然后，我们往Model类添加class方法，就可以让所有子类调用class方法：

# class Model(dict):

#     ...

#     @classmethod
#     @asyncio.coroutine
#     def find(cls, pk):
#         ' find object by primary key. '
#         rs = yield from select('%s where `%s`=?' % (cls.__select__, cls.__primary_key__), [pk], 1)
#         if len(rs) == 0:
#             return None
#         return cls(**rs[0])

#  user = yield from User.find('123')

#  往Model类添加实例方法，就可以让所有子类调用实例方法：
# class Model(dict):

#     @classmethod
#     @asyncio.coroutine
#     def save(self):
#         args = list(map(self.getValueOrDefault,self.__fields__))
#         args.append(self.getValueOrDefault(self.__primary_key__))
#         rows = yield from execute(self.__insert__, args)
#         if rows != 1:
#             logging.warn('failed to insert record: affected rows:%s' % rows)


#  
class IntegerField(Field):

    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)

class BooleanField(Field):

    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)

class FloatField(Field):

    def __init__(self, name=None, primary_key=False, default=0.0):
        super().__init__(name, 'real', primary_key, default)

class TextField(Field):

    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default)

# from orm import Model, StringField,IntegerField
# class User(Model):
#     __tables__ = 'users'

#     id = IntegerField(primary_key=True)
#     name = StringField()

 # user = User(id=123, name='Michael')
 # yield from user.save()