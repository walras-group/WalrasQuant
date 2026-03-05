HyperLiquid Exchange
====================

HyperLiquid Account Types
-------------------------

.. code-block:: python

   from walrasquant.exchange.hyperliquid import HyperLiquidAccountType

   account_type = HyperLiquidAccountType.TESTNET

Common options include:

- ``HyperLiquidAccountType.MAINNET``
- ``HyperLiquidAccountType.TESTNET``
- ``HyperLiquidAccountType.SPOT_MOCK`` / ``LINEAR_MOCK`` / ``INVERSE_MOCK``

HyperLiquid Config
------------------

.. code-block:: python

   from walrasquant.constants import ExchangeType, settings
   from walrasquant.exchange.hyperliquid import HyperLiquidAccountType
   from walrasquant.config import (
       Config,
       PublicConnectorConfig,
       PrivateConnectorConfig,
       BasicConfig,
   )

   # For HyperLiquid, api_key is wallet address and secret is agent private key
   HYPERLIQUID_API_KEY = settings.HYPERLIQUID.TESTNET.api_key
   HYPERLIQUID_SECRET = settings.HYPERLIQUID.TESTNET.secret

   config = Config(
       strategy_id="hyperliquid_demo",
       user_id="user_test",
       strategy=Demo(),
       basic_config={
           ExchangeType.HYPERLIQUID: BasicConfig(
               api_key=HYPERLIQUID_API_KEY,
               secret=HYPERLIQUID_SECRET,
               testnet=True,
           )
       },
       public_conn_config={
           ExchangeType.HYPERLIQUID: [
               PublicConnectorConfig(account_type=HyperLiquidAccountType.TESTNET),
           ]
       },
       private_conn_config={
           ExchangeType.HYPERLIQUID: [
               PrivateConnectorConfig(account_type=HyperLiquidAccountType.TESTNET),
           ]
       },
   )
