# vn.py框架的PostgreSQL数据库接口

<p align="center">
  <img src ="https://vnpy.oss-cn-shanghai.aliyuncs.com/vnpy-logo.png"/>
</p>

<p align="center">
    <img src ="https://img.shields.io/badge/version-1.0.0-blueviolet.svg"/>
    <img src ="https://img.shields.io/badge/platform-windows|linux|macos-yellow.svg"/>
    <img src ="https://img.shields.io/badge/python-3.7-blue.svg" />
</p>

## 说明

基于peewee开发的PostgreSQL数据库接口。

## 使用

PostgreSQL在VN Trader中配置时，需要填写以下字段信息：

| 字段名            | 值 |
|---------           |---- |
|database.driver     | "postgresql" |
|database.host       | 地址 |
|database.port       | 端口 |
|database.database   | 数据库名 |
|database.user       | 用户名 |
|database.password   | 密码 |
 
PostgreSQL的例子如下所示：

| 字段名            | 值 |
|---------           |----  |
|database.driver     | postgresql |
|database.host       | localhost |
|database.port       | 5432 |
|database.database   | vnpy |
|database.user       | postgre |
|database.password   | .... |

请注意，vn.py不会主动为关系型数据库创建数据库，所以请确保你所填的database.database字段对应的数据库已经创建好了。若未创建数据库，请手动连上数据库并创建。
