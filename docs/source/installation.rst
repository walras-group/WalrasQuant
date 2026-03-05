Installation
============

Prerequisites
-------------

- Python ``>=3.11,<3.14``
- Redis (optional, only needed when using ``StorageType.REDIS``)
- Linux or macOS recommended

Install from PyPI
-----------------

.. code-block:: bash

   pip install walrasquant

Install from source
-------------------

.. code-block:: bash

   git clone https://github.com/walras-group/WalrasQuant.git
   cd WalrasQuant
   uv pip install -e .

Optional: Redis setup
---------------------

WalrasQuant defaults to ``StorageType.SQLITE`` via ``Config.storage_backend``.
If you switch to ``StorageType.REDIS``, configure Redis in your ``.env`` file:

.. code-block:: bash

   NEXUS_REDIS_HOST=127.0.0.1
   NEXUS_REDIS_PORT=6379
   NEXUS_REDIS_DB=0
   NEXUS_REDIS_PASSWORD=your_password

Start Redis using Docker Compose:

.. code-block:: bash

   docker-compose up -d redis

Minimal config example
----------------------

.. code-block:: python

   from walrasquant.config import Config
   from walrasquant.constants import StorageType

   config = Config(
       strategy_id="demo",
       user_id="user_test",
       strategy=...,  # your Strategy instance
       basic_config={},
       public_conn_config={},
       storage_backend=StorageType.SQLITE,
   )
