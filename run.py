#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Скрипт для запуска бота из корневой директории проекта.
"""

import asyncio
import logging
from src.bot import main

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(main()) 