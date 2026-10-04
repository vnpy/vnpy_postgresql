"""PostgreSQL的K线与Tick存储实现。"""

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol, cast

from peewee import (
    Asc,
    AutoField,
    CharField,
    DateTimeField,
    Desc,
    FloatField,
    IntegerField,
    Model,
    PostgresqlDatabase as PeeweePostgresqlDatabase,
    ModelSelect,
    ModelDelete,
    fn,
    chunked,
    EXCLUDED
)

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData, TickData
from vnpy.trader.database import (
    BaseDatabase,
    BarOverview,
    TickOverview,
    DB_TZ,
    convert_tz
)
from vnpy.trader.setting import SETTINGS


db: PeeweePostgresqlDatabase = PeeweePostgresqlDatabase(
    database=SETTINGS["database.database"],
    user=SETTINGS["database.user"],
    password=SETTINGS["database.password"],
    host=SETTINGS["database.host"],
    port=SETTINGS["database.port"],
    autorollback=True
)


class DbBarData(Model):
    """K线数据表映射对象"""

    id: AutoField = AutoField()

    symbol: CharField = CharField()
    exchange: CharField = CharField()
    datetime: DateTimeField = DateTimeField()
    interval: CharField = CharField()

    volume: FloatField = FloatField()
    turnover: FloatField = FloatField()
    open_interest: FloatField = FloatField()
    open_price: FloatField = FloatField()
    high_price: FloatField = FloatField()
    low_price: FloatField = FloatField()
    close_price: FloatField = FloatField()

    class Meta:
        """绑定数据库，并以合约、交易所、周期和时间建立唯一索引。"""
        database: PeeweePostgresqlDatabase = db
        indexes: tuple = ((("symbol", "exchange", "interval", "datetime"), True),)


class DbTickData(Model):
    """TICK数据表映射对象"""

    id: AutoField = AutoField()

    symbol: CharField = CharField()
    exchange: CharField = CharField()
    datetime: DateTimeField = DateTimeField()

    name: CharField = CharField()
    volume: FloatField = FloatField()
    turnover: FloatField = FloatField()
    open_interest: FloatField = FloatField()
    last_price: FloatField = FloatField()
    last_volume: FloatField = FloatField()
    limit_up: FloatField = FloatField()
    limit_down: FloatField = FloatField()

    open_price: FloatField = FloatField()
    high_price: FloatField = FloatField()
    low_price: FloatField = FloatField()
    pre_close: FloatField = FloatField()

    bid_price_1: FloatField = FloatField()
    bid_price_2: FloatField = FloatField(null=True)
    bid_price_3: FloatField = FloatField(null=True)
    bid_price_4: FloatField = FloatField(null=True)
    bid_price_5: FloatField = FloatField(null=True)

    ask_price_1: FloatField = FloatField()
    ask_price_2: FloatField = FloatField(null=True)
    ask_price_3: FloatField = FloatField(null=True)
    ask_price_4: FloatField = FloatField(null=True)
    ask_price_5: FloatField = FloatField(null=True)

    bid_volume_1: FloatField = FloatField()
    bid_volume_2: FloatField = FloatField(null=True)
    bid_volume_3: FloatField = FloatField(null=True)
    bid_volume_4: FloatField = FloatField(null=True)
    bid_volume_5: FloatField = FloatField(null=True)

    ask_volume_1: FloatField = FloatField()
    ask_volume_2: FloatField = FloatField(null=True)
    ask_volume_3: FloatField = FloatField(null=True)
    ask_volume_4: FloatField = FloatField(null=True)
    ask_volume_5: FloatField = FloatField(null=True)

    localtime: DateTimeField = DateTimeField(null=True)

    class Meta:
        """绑定数据库，并以合约、交易所和时间建立唯一索引。"""
        database: PeeweePostgresqlDatabase = db
        indexes: tuple = ((("symbol", "exchange", "datetime"), True),)


class DbBarOverview(Model):
    """K线汇总数据表映射对象"""

    id: AutoField = AutoField()

    # 实例上读写到的是 Python 值；cast 不改变运行时的字段对象
    symbol: str = cast(str, CharField())
    exchange: str = cast(str, CharField())
    interval: str = cast(str, CharField())
    count: int = cast(int, IntegerField())
    start: datetime = cast(datetime, DateTimeField())
    end: datetime = cast(datetime, DateTimeField())

    class Meta:
        """绑定数据库，并以合约、交易所和周期建立唯一索引。"""
        database: PeeweePostgresqlDatabase = db
        indexes: tuple = ((("symbol", "exchange", "interval"), True),)


class DbTickOverview(Model):
    """Tick汇总数据表映射对象"""

    id: AutoField = AutoField()

    # 实例上读写到的是 Python 值；cast 不改变运行时的字段对象
    symbol: str = cast(str, CharField())
    exchange: str = cast(str, CharField())
    count: int = cast(int, IntegerField())
    start: datetime = cast(datetime, DateTimeField())
    end: datetime = cast(datetime, DateTimeField())

    class Meta:
        """绑定数据库，并以合约和交易所建立唯一索引。"""
        database: PeeweePostgresqlDatabase = db
        indexes: tuple = ((("symbol", "exchange"), True),)


class _BarRow(Protocol):
    """K线查询行在运行时读到的 Python 值。"""

    symbol: str
    exchange: str
    datetime: datetime
    interval: str
    volume: float
    turnover: float
    open_interest: float
    open_price: float
    high_price: float
    low_price: float
    close_price: float


class _TickRow(Protocol):
    """Tick查询行在运行时读到的 Python 值。"""

    localtime: datetime | None
    symbol: str
    exchange: str
    datetime: datetime
    name: str
    volume: float
    turnover: float
    open_interest: float
    last_price: float
    last_volume: float
    limit_up: float
    limit_down: float
    open_price: float
    high_price: float
    low_price: float
    pre_close: float
    bid_price_1: float
    bid_price_2: float
    bid_price_3: float
    bid_price_4: float
    bid_price_5: float
    ask_price_1: float
    ask_price_2: float
    ask_price_3: float
    ask_price_4: float
    ask_price_5: float
    bid_volume_1: float
    bid_volume_2: float
    bid_volume_3: float
    bid_volume_4: float
    bid_volume_5: float
    ask_volume_1: float
    ask_volume_2: float
    ask_volume_3: float
    ask_volume_4: float
    ask_volume_5: float


class _BarGroupRow(Protocol):
    """分组汇总行只包含合约、交易所、周期和根数。"""

    symbol: str
    exchange: str
    interval: str
    count: int


class PostgresqlDatabase(BaseDatabase):
    """PostgreSQL数据库接口"""

    def __init__(self) -> None:
        """连接数据库并创建K线、Tick及其汇总表。"""
        self.db: PeeweePostgresqlDatabase = db
        self.db.connect(reuse_if_open=True)
        self.db.create_tables([DbBarData, DbTickData, DbBarOverview, DbTickOverview])

    def save_bar_data(self, bars: list[BarData], stream: bool = False) -> bool:
        """保存K线数据"""
        # 读取主键参数
        bar: BarData = bars[0]
        symbol: str = bar.symbol
        exchange: Exchange = bar.exchange
        interval: Interval = cast(Interval, bar.interval)

        # 将BarData数据转换为字典，并调整时区
        data: list = []

        for bar in bars:
            bar.datetime = convert_tz(bar.datetime)

            d: dict = bar.__dict__
            d["exchange"] = d["exchange"].value
            d["interval"] = d["interval"].value
            d.pop("gateway_name")
            d.pop("vt_symbol")
            d.pop("extra", None)
            data.append(d)

        # 使用upsert操作将数据更新到数据库中 chunked批量操作加快速度
        with self.db.atomic():
            c: list[dict]
            for c in chunked(data, 100):
                DbBarData.insert_many(c).on_conflict(
                    update={
                        DbBarData.volume: EXCLUDED.volume,
                        DbBarData.turnover: EXCLUDED.turnover,
                        DbBarData.open_interest: EXCLUDED.open_interest,
                        DbBarData.open_price: EXCLUDED.open_price,
                        DbBarData.high_price: EXCLUDED.high_price,
                        DbBarData.low_price: EXCLUDED.low_price,
                        DbBarData.close_price: EXCLUDED.close_price
                    },
                    conflict_target=(
                        DbBarData.symbol,
                        DbBarData.exchange,
                        DbBarData.interval,
                        DbBarData.datetime,
                    ),
                ).execute()

        # 更新K线汇总数据
        overview: DbBarOverview | None = DbBarOverview.get_or_none(
            DbBarOverview.symbol == symbol,
            DbBarOverview.exchange == exchange.value,
            DbBarOverview.interval == interval.value,
        )

        if not overview:
            overview = DbBarOverview()
            overview.symbol = symbol
            overview.exchange = exchange.value
            overview.interval = interval.value
            overview.start = bars[0].datetime
            overview.end = bars[-1].datetime
            overview.count = len(bars)
        elif stream:
            overview.end = bars[-1].datetime
            overview.count += len(bars)
        else:
            overview.start = min(bars[0].datetime, overview.start)
            overview.end = max(bars[-1].datetime, overview.end)

            s: ModelSelect[DbBarData] = DbBarData.select().where(
                (DbBarData.symbol == symbol)
                & (DbBarData.exchange == exchange.value)
                & (DbBarData.interval == interval.value)
            )
            overview.count = s.count()

        overview.save()

        return True

    def save_tick_data(self, ticks: list[TickData], stream: bool = False) -> bool:
        """保存TICK数据"""
        # 读取主键参数
        tick: TickData = ticks[0]
        symbol: str = tick.symbol
        exchange: Exchange = tick.exchange

        # 将TickData数据转换为字典，并调整时区
        data: list = []

        for tick in ticks:
            tick.datetime = convert_tz(tick.datetime)

            d: dict = tick.__dict__
            d["exchange"] = d["exchange"].value
            d.pop("gateway_name")
            d.pop("vt_symbol")
            d.pop("extra", None)
            data.append(d)

        # 使用upsert操作将数据更新到数据库中
        with self.db.atomic():
            c: list[dict]
            for c in chunked(data, 100):
                DbTickData.insert_many(c).on_conflict(
                    update={
                        DbTickData.name: EXCLUDED.name,
                        DbTickData.volume: EXCLUDED.volume,
                        DbTickData.turnover: EXCLUDED.turnover,
                        DbTickData.open_interest: EXCLUDED.open_interest,
                        DbTickData.last_price: EXCLUDED.last_price,
                        DbTickData.last_volume: EXCLUDED.last_volume,
                        DbTickData.limit_up: EXCLUDED.limit_up,
                        DbTickData.limit_down: EXCLUDED.limit_down,
                        DbTickData.open_price: EXCLUDED.open_price,
                        DbTickData.high_price: EXCLUDED.high_price,
                        DbTickData.low_price: EXCLUDED.low_price,
                        DbTickData.pre_close: EXCLUDED.pre_close,
                        DbTickData.bid_price_1: EXCLUDED.bid_price_1,
                        DbTickData.bid_price_2: EXCLUDED.bid_price_2,
                        DbTickData.bid_price_3: EXCLUDED.bid_price_3,
                        DbTickData.bid_price_4: EXCLUDED.bid_price_4,
                        DbTickData.bid_price_5: EXCLUDED.bid_price_5,
                        DbTickData.ask_price_1: EXCLUDED.ask_price_1,
                        DbTickData.ask_price_2: EXCLUDED.ask_price_2,
                        DbTickData.ask_price_3: EXCLUDED.ask_price_3,
                        DbTickData.ask_price_4: EXCLUDED.ask_price_4,
                        DbTickData.ask_price_5: EXCLUDED.ask_price_5,
                        DbTickData.bid_volume_1: EXCLUDED.bid_volume_1,
                        DbTickData.bid_volume_2: EXCLUDED.bid_volume_2,
                        DbTickData.bid_volume_3: EXCLUDED.bid_volume_3,
                        DbTickData.bid_volume_4: EXCLUDED.bid_volume_4,
                        DbTickData.bid_volume_5: EXCLUDED.bid_volume_5,
                        DbTickData.ask_volume_1: EXCLUDED.ask_volume_1,
                        DbTickData.ask_volume_2: EXCLUDED.ask_volume_2,
                        DbTickData.ask_volume_3: EXCLUDED.ask_volume_3,
                        DbTickData.ask_volume_4: EXCLUDED.ask_volume_4,
                        DbTickData.ask_volume_5: EXCLUDED.ask_volume_5,
                        DbTickData.localtime: EXCLUDED.localtime,
                    },
                    conflict_target=(
                        DbTickData.symbol,
                        DbTickData.exchange,
                        DbTickData.datetime,
                    ),
                ).execute()

        # 更新Tick汇总数据
        overview: DbTickOverview | None = DbTickOverview.get_or_none(
            DbTickOverview.symbol == symbol,
            DbTickOverview.exchange == exchange.value,
        )

        if not overview:
            overview = DbTickOverview()
            overview.symbol = symbol
            overview.exchange = exchange.value
            overview.start = ticks[0].datetime
            overview.end = ticks[-1].datetime
            overview.count = len(ticks)
        elif stream:
            overview.end = ticks[-1].datetime
            overview.count += len(ticks)
        else:
            overview.start = min(ticks[0].datetime, overview.start)
            overview.end = max(ticks[-1].datetime, overview.end)

            s: ModelSelect[DbTickData] = DbTickData.select().where(
                (DbTickData.symbol == symbol)
                & (DbTickData.exchange == exchange.value)
            )
            overview.count = s.count()

        overview.save()

        return True

    def load_bar_data(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        start: datetime,
        end: datetime
    ) -> list[BarData]:
        """读取K线数据"""
        s: ModelSelect[DbBarData] = (
            DbBarData.select().where(
                (DbBarData.symbol == symbol)
                & (DbBarData.exchange == exchange.value)
                & (DbBarData.interval == interval.value)
                & (DbBarData.datetime >= start)
                & (DbBarData.datetime <= end)
            ).order_by(DbBarData.datetime)
        )

        bars: list[BarData] = []
        for db_bar in cast(Iterable[_BarRow], s):
            bar: BarData = BarData(
                symbol=db_bar.symbol,
                exchange=Exchange(db_bar.exchange),
                datetime=datetime.fromtimestamp(db_bar.datetime.timestamp(), DB_TZ),
                interval=Interval(db_bar.interval),
                volume=db_bar.volume,
                turnover=db_bar.turnover,
                open_interest=db_bar.open_interest,
                open_price=db_bar.open_price,
                high_price=db_bar.high_price,
                low_price=db_bar.low_price,
                close_price=db_bar.close_price,
                gateway_name="DB"
            )
            bars.append(bar)

        return bars

    def load_tick_data(
        self,
        symbol: str,
        exchange: Exchange,
        start: datetime,
        end: datetime
    ) -> list[TickData]:
        """读取TICK数据"""
        s: ModelSelect[DbTickData] = (
            DbTickData.select().where(
                (DbTickData.symbol == symbol)
                & (DbTickData.exchange == exchange.value)
                & (DbTickData.datetime >= start)
                & (DbTickData.datetime <= end)
            ).order_by(DbTickData.datetime)
        )

        ticks: list[TickData] = []
        for db_tick in cast(Iterable[_TickRow], s):
            tick: TickData = TickData(
                symbol=db_tick.symbol,
                exchange=Exchange(db_tick.exchange),
                datetime=datetime.fromtimestamp(db_tick.datetime.timestamp(), DB_TZ),
                name=db_tick.name,
                volume=db_tick.volume,
                turnover=db_tick.turnover,
                open_interest=db_tick.open_interest,
                last_price=db_tick.last_price,
                last_volume=db_tick.last_volume,
                limit_up=db_tick.limit_up,
                limit_down=db_tick.limit_down,
                open_price=db_tick.open_price,
                high_price=db_tick.high_price,
                low_price=db_tick.low_price,
                pre_close=db_tick.pre_close,
                bid_price_1=db_tick.bid_price_1,
                bid_price_2=db_tick.bid_price_2,
                bid_price_3=db_tick.bid_price_3,
                bid_price_4=db_tick.bid_price_4,
                bid_price_5=db_tick.bid_price_5,
                ask_price_1=db_tick.ask_price_1,
                ask_price_2=db_tick.ask_price_2,
                ask_price_3=db_tick.ask_price_3,
                ask_price_4=db_tick.ask_price_4,
                ask_price_5=db_tick.ask_price_5,
                bid_volume_1=db_tick.bid_volume_1,
                bid_volume_2=db_tick.bid_volume_2,
                bid_volume_3=db_tick.bid_volume_3,
                bid_volume_4=db_tick.bid_volume_4,
                bid_volume_5=db_tick.bid_volume_5,
                ask_volume_1=db_tick.ask_volume_1,
                ask_volume_2=db_tick.ask_volume_2,
                ask_volume_3=db_tick.ask_volume_3,
                ask_volume_4=db_tick.ask_volume_4,
                ask_volume_5=db_tick.ask_volume_5,
                localtime=db_tick.localtime,
                gateway_name="DB"
            )
            ticks.append(tick)

        return ticks

    def delete_bar_data(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval
    ) -> int:
        """删除K线数据"""
        d: ModelDelete = DbBarData.delete().where(
            (DbBarData.symbol == symbol)
            & (DbBarData.exchange == exchange.value)
            & (DbBarData.interval == interval.value)
        )
        count: int = d.execute()

        # 删除K线汇总数据
        d2: ModelDelete = DbBarOverview.delete().where(
            (DbBarOverview.symbol == symbol)
            & (DbBarOverview.exchange == exchange.value)
            & (DbBarOverview.interval == interval.value)
        )
        d2.execute()
        return count

    def delete_tick_data(
        self,
        symbol: str,
        exchange: Exchange
    ) -> int:
        """删除TICK数据"""
        d: ModelDelete = DbTickData.delete().where(
            (DbTickData.symbol == symbol)
            & (DbTickData.exchange == exchange.value)
        )
        count: int = d.execute()

        # 删除Tick汇总数据
        d2: ModelDelete = DbTickOverview.delete().where(
            (DbTickOverview.symbol == symbol)
            & (DbTickOverview.exchange == exchange.value)
        )
        d2.execute()

        return count

    def get_bar_overview(self) -> list[BarOverview]:
        """查询数据库中的K线汇总信息"""
        # 如果已有K线，但缺失汇总信息，则执行初始化
        data_count: int = DbBarData.select().count()
        overview_count: int = DbBarOverview.select().count()
        if data_count and not overview_count:
            self.init_bar_overview()

        s: ModelSelect[DbBarOverview] = DbBarOverview.select()
        overviews: list[BarOverview] = []
        for overview in cast(Iterable[BarOverview], s):
            overview.exchange = Exchange(overview.exchange)
            overview.interval = Interval(overview.interval)
            overviews.append(overview)
        return overviews

    def get_tick_overview(self) -> list[TickOverview]:
        """查询数据库中的Tick汇总信息"""
        s: ModelSelect[DbTickOverview] = DbTickOverview.select()
        overviews: list = []
        for overview in cast(Iterable[TickOverview], s):
            overview.exchange = Exchange(overview.exchange)
            overviews.append(overview)
        return overviews

    def init_bar_overview(self) -> None:
        """初始化数据库中的K线汇总信息"""
        s: ModelSelect[DbBarData] = (
            DbBarData.select(
                DbBarData.symbol,
                DbBarData.exchange,
                DbBarData.interval,
                fn.COUNT(DbBarData.id).alias("count")
            ).group_by(
                DbBarData.symbol,
                DbBarData.exchange,
                DbBarData.interval
            )
        )

        for data in cast(Iterable[_BarGroupRow], s):
            overview: DbBarOverview = DbBarOverview()
            overview.symbol = data.symbol
            overview.exchange = data.exchange
            overview.interval = data.interval
            overview.count = data.count

            start_bar: DbBarData = (
                DbBarData.select()
                .where(
                    (DbBarData.symbol == data.symbol)
                    & (DbBarData.exchange == data.exchange)
                    & (DbBarData.interval == data.interval)
                )
                .order_by(Asc(DbBarData.datetime))
                .first()
            )
            overview.start = cast(datetime, start_bar.datetime)

            end_bar: DbBarData = (
                DbBarData.select()
                .where(
                    (DbBarData.symbol == data.symbol)
                    & (DbBarData.exchange == data.exchange)
                    & (DbBarData.interval == data.interval)
                )
                .order_by(Desc(DbBarData.datetime))
                .first()
            )
            overview.end = cast(datetime, end_bar.datetime)

            overview.save()
