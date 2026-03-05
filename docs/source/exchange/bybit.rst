Bybit Exchange
==============

Bybit Account Types
-------------------

.. code-block:: python

   from walrasquant.exchange.bybit import BybitAccountType

   account_type = BybitAccountType.UNIFIED_TESTNET

Common options include:

- ``BybitAccountType.SPOT`` / ``SPOT_TESTNET``
- ``BybitAccountType.LINEAR`` / ``LINEAR_TESTNET``
- ``BybitAccountType.INVERSE`` / ``INVERSE_TESTNET``
- ``BybitAccountType.OPTION`` / ``OPTION_TESTNET``
- ``BybitAccountType.UNIFIED`` / ``UNIFIED_TESTNET``
- ``BybitAccountType.SPOT_MOCK`` / ``LINEAR_MOCK`` / ``INVERSE_MOCK``

Bybit Config
------------

.. code-block:: python

   from walrasquant.constants import ExchangeType, settings
   from walrasquant.exchange.bybit import BybitAccountType
   from walrasquant.config import (
       Config,
       PublicConnectorConfig,
       PrivateConnectorConfig,
       BasicConfig,
   )

   BYBIT_API_KEY = settings.BYBIT.TESTNET.api_key
   BYBIT_SECRET = settings.BYBIT.TESTNET.secret

   config = Config(
       strategy_id="bybit_demo",
       user_id="user_test",
       strategy=Demo(),
       basic_config={
           ExchangeType.BYBIT: BasicConfig(
               api_key=BYBIT_API_KEY,
               secret=BYBIT_SECRET,
               testnet=True,
           )
       },
       public_conn_config={
           ExchangeType.BYBIT: [
               PublicConnectorConfig(account_type=BybitAccountType.LINEAR_TESTNET),
               PublicConnectorConfig(account_type=BybitAccountType.SPOT_TESTNET),
           ]
       },
       private_conn_config={
           ExchangeType.BYBIT: [
               PrivateConnectorConfig(account_type=BybitAccountType.UNIFIED_TESTNET),
           ]
       },
   )
