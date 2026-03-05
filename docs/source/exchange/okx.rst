OKX Exchange
============

OKX Account Types
-----------------

.. code-block:: python

   from walrasquant.exchange.okx import OkxAccountType

   account_type = OkxAccountType.DEMO

Common options include:

- ``OkxAccountType.LIVE``
- ``OkxAccountType.DEMO``
- ``OkxAccountType.SPOT_MOCK`` / ``LINEAR_MOCK`` / ``INVERSE_MOCK``

OKX Config
----------

.. code-block:: python

   from walrasquant.constants import ExchangeType, settings
   from walrasquant.exchange.okx import OkxAccountType
   from walrasquant.config import (
       Config,
       PublicConnectorConfig,
       PrivateConnectorConfig,
       BasicConfig,
   )

   OKX_API_KEY = settings.OKX.DEMO.api_key
   OKX_SECRET = settings.OKX.DEMO.secret
   OKX_PASSPHRASE = settings.OKX.DEMO.passphrase

   config = Config(
       strategy_id="okx_demo",
       user_id="user_test",
       strategy=Demo(),
       basic_config={
           ExchangeType.OKX: BasicConfig(
               api_key=OKX_API_KEY,
               secret=OKX_SECRET,
               passphrase=OKX_PASSPHRASE,
               testnet=True,
           )
       },
       public_conn_config={
           ExchangeType.OKX: [
               PublicConnectorConfig(account_type=OkxAccountType.DEMO),
           ]
       },
       private_conn_config={
           ExchangeType.OKX: [
               PrivateConnectorConfig(account_type=OkxAccountType.DEMO),
           ]
       },
   )
