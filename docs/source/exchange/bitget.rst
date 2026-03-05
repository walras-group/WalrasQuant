Bitget Exchange
===============

Bitget Account Types
--------------------

.. code-block:: python

   from walrasquant.exchange.bitget import BitgetAccountType

   account_type = BitgetAccountType.FUTURE_DEMO

Common options include:

- ``BitgetAccountType.UTA`` / ``BitgetAccountType.UTA_DEMO``
- ``BitgetAccountType.SPOT`` / ``BitgetAccountType.SPOT_DEMO``
- ``BitgetAccountType.FUTURE`` / ``BitgetAccountType.FUTURE_DEMO``
- ``BitgetAccountType.SPOT_MOCK`` / ``LINEAR_MOCK`` / ``INVERSE_MOCK``

Bitget Config
-------------

.. code-block:: python

   from walrasquant.constants import ExchangeType, settings
   from walrasquant.exchange.bitget import BitgetAccountType
   from walrasquant.config import (
       Config,
       PublicConnectorConfig,
       PrivateConnectorConfig,
       BasicConfig,
   )

   BITGET_API_KEY = settings.BITGET.TESTNET.api_key
   BITGET_SECRET = settings.BITGET.TESTNET.secret

   config = Config(
       strategy_id="bitget_demo",
       user_id="user_test",
       strategy=Demo(),
       basic_config={
           ExchangeType.BITGET: BasicConfig(
               api_key=BITGET_API_KEY,
               secret=BITGET_SECRET,
               testnet=True,
           )
       },
       public_conn_config={
           ExchangeType.BITGET: [
               PublicConnectorConfig(account_type=BitgetAccountType.FUTURE_DEMO),
           ]
       },
       private_conn_config={
           ExchangeType.BITGET: [
               PrivateConnectorConfig(account_type=BitgetAccountType.FUTURE_DEMO),
           ]
       },
   )
