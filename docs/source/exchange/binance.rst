Binance Exchange
================

Binance Account Types
---------------------

.. code-block:: python

   from walrasquant.exchange.binance import BinanceAccountType

   account_type = BinanceAccountType.USD_M_FUTURE_TESTNET

Common options include:

- ``BinanceAccountType.SPOT`` / ``SPOT_TESTNET``
- ``BinanceAccountType.USD_M_FUTURE`` / ``USD_M_FUTURE_TESTNET``
- ``BinanceAccountType.COIN_M_FUTURE`` / ``COIN_M_FUTURE_TESTNET``
- ``BinanceAccountType.MARGIN`` / ``ISOLATED_MARGIN`` / ``PORTFOLIO_MARGIN``
- ``BinanceAccountType.SPOT_MOCK`` / ``LINEAR_MOCK`` / ``INVERSE_MOCK``

Binance Config
--------------

.. code-block:: python

   from walrasquant.constants import ExchangeType, settings
   from walrasquant.exchange.binance import BinanceAccountType
   from walrasquant.config import (
       Config,
       PublicConnectorConfig,
       PrivateConnectorConfig,
       BasicConfig,
   )

   BINANCE_API_KEY = settings.BINANCE.TESTNET.api_key
   BINANCE_SECRET = settings.BINANCE.TESTNET.secret

   config = Config(
       strategy_id="binance_demo",
       user_id="user_test",
       strategy=Demo(),
       basic_config={
           ExchangeType.BINANCE: BasicConfig(
               api_key=BINANCE_API_KEY,
               secret=BINANCE_SECRET,
               testnet=True,
           )
       },
       public_conn_config={
           ExchangeType.BINANCE: [
               PublicConnectorConfig(
                   account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
               )
           ]
       },
       private_conn_config={
           ExchangeType.BINANCE: [
               PrivateConnectorConfig(
                   account_type=BinanceAccountType.USD_M_FUTURE_TESTNET,
               )
           ]
       },
   )
