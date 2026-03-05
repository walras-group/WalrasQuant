Welcome to WalrasQuant's documentation!
=======================================

.. |python-versions| image:: https://img.shields.io/badge/python-3.11%20|%203.12%20|%203.13-blue
   :alt: Python Versions

.. |docs| image:: https://img.shields.io/badge/docs-passing-brightgreen
   :alt: Documentation Status

.. |version| image:: https://img.shields.io/pypi/v/walrasquant?&color=blue
   :alt: Version

.. only:: html

   |python-versions| |docs| |version|

Introduction
------------

WalrasQuant is a high-performance Python framework for quantitative trading.
It is designed for low-latency execution, multi-exchange connectivity, and
strategy development at scale.

Core Advantages
---------------

- Async-first architecture for real-time trading workflows.
- Exchange integrations for Binance, OKX, Bybit, HyperLiquid, and Bitget.
- Strategy framework with execution algorithms (including TWAP).
- Built-in order and position lifecycle management.
- Optional FastAPI integration for runtime APIs.
- CLI and PM2 tooling for operations.

Architecture (Data Flow)
------------------------

The core abstraction in WalrasQuant is the ``Connector``. ``PublicConnector``
handles market data streams, while ``PrivateConnector`` manages account state
and order lifecycle callbacks. Order submission is handled by EMS modules, and
order state tracking/routing is handled by OMS modules before data is delivered
back to ``Strategy`` callbacks.

.. image:: ./_static/arch.png
   :alt: Data Flow Diagram
   :align: center

Contact
-------

.. |twitter| image:: https://img.shields.io/badge/X-000000?&logo=x&logoColor=white
   :target: https://x.com/quantweb3_ai

.. |discord| image:: https://img.shields.io/badge/Discord-5865F2?&logo=discord&logoColor=white
   :target: https://discord.gg/BR8VGRrXFr

.. |telegram| image:: https://img.shields.io/badge/Telegram-2CA5E0?&logo=telegram&logoColor=white
   :target: https://t.me/+6e2MtXxoibM2Yzlk

.. only:: html

   |twitter| Stay updated with our latest news, features, and announcements.

.. only:: html

   |discord| Join our community to discuss ideas, get support, and connect with other users.

.. only:: html

   |telegram| Receive instant updates and engage in real-time discussions.

Contents
--------

.. toctree::
   :maxdepth: 2

   installation
   quickstart/index
   concepts/index
   exchange/index
   api/index
