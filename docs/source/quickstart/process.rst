Process Management
==================

In this section, you'll learn how to manage strategy processes with ``wq``.

Prerequisites
-------------

Install PM2 (required by ``wq``):

.. code-block:: bash

   npm install -g pm2

Install ``hl`` for log viewing (optional, used by ``wq logs``):

.. code-block:: bash

   # https://github.com/pamburus/hl
   hl --version

Start a strategy
----------------

``wq start`` runs your strategy script via PM2.
If ``strategy_id`` and ``user_id`` are not passed, ``wq`` extracts them from ``Config(...)`` in the script.

.. code-block:: bash

   wq start strategy/okx/buy_and_cancel.py

You can also pass ids explicitly:

.. code-block:: bash

   wq start strategy/okx/buy_and_cancel.py -s okx_buy_and_sell -u user_test

List processes
--------------

.. code-block:: bash

   wq ls

View logs
---------

.. code-block:: bash

   wq log okx_buy_and_sell.user_test
   wq log okx_buy_and_sell.user_test -F
   wq log okx_buy_and_sell.user_test -d 3

Stop / restart / delete
-----------------------

.. code-block:: bash

   wq stop okx_buy_and_sell.user_test
   wq restart okx_buy_and_sell.user_test
   wq delete okx_buy_and_sell.user_test
