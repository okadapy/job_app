import asyncio
import json
from typing import Optional, Union, Dict, Any

import sqlalchemy as sa
from sqlalchemy import ForeignKey
from sqlalchemy.orm import DeclarativeBase, Session
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy import String
from aiogram.types import (
    Message,
    User,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
    WebAppData,
)
from aiogram import Dispatcher, Bot
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command, Filter
import aiohttp

DEFAULT_HEADERS = {"Content-Type": "application/json", "Accept": "*/*"}
AMPLITUDE_KEY = "<KEY HERE>"
TG_KEY = "<KEY HERE>"
dp = Dispatcher()


class Base(DeclarativeBase):
    pass


class WebAppDataFilter(Filter):
    async def __call__(self, message: Message, **kwargs) -> Union[bool, Dict[str, Any]]:
        return (
            dict(web_app_data=message.web_app_data) if message.web_app_data else False
        )


class TextMessage(Filter):
    async def __call__(self, message: Message, **kwargs) -> Union[bool, Message]:
        return message if message.text else False


class Characters(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str]
    greeting_text: Mapped[str]
    system_prompt: Mapped[str]


class Users(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    surname: Mapped[Optional[str]]
    character: Mapped[Optional[str]] = mapped_column(default="Марио")
    time: Mapped[int] = mapped_column(default=sa.func.localtimestamp())

    def __repr__(self):
        return f"ID: {self.id}, UNAME: {self.username}, NAME: {self.name}, SURNAME: {self.surname}, REGISTERED: {self.time}"


class Messages(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_user: Mapped[int] = mapped_column(ForeignKey("users.id"))
    message: Mapped[str]
    time: Mapped[int] = mapped_column(default=sa.func.localtimestamp())

    def __repr__(self):
        return f"ID: {self.id}, FROM USER: {self.from_user}, MESSAGE: {self.message}, TIME: {self.time}"


class Replies(Base):
    __tablename__ = "replies"

    id: Mapped[int] = mapped_column(primary_key=True)
    to_message: Mapped[int] = mapped_column(ForeignKey("messages.id"))
    message: Mapped[str]
    time: Mapped[int] = mapped_column(default=sa.func.localtimestamp())

    def __repr__(self):
        return f"ID: {self.id}, TO MESSAGE: {self.to_message}, MESSAGE: {self.message}"


async def update_character(user: User, character: str) -> None:
    data = {
        "api_key": AMPLITUDE_KEY,
        "events": [{"user_id": user.id, "event_type": "character chosen"}],
    }

    stmt = sa.update(Users).where(Users.id == user.id).values(character=character)
    db.execute(stmt)
    db.commit()
    stmt = sa.select(Users).where(Users.id == user.id)
    print(db.scalar(stmt).character, character)

    async with aiohttp.ClientSession("https://api2.amplitude.com") as session:
        async with session.post(
            "/2/httpapi", headers=DEFAULT_HEADERS, data=json.dumps(data)
        ) as resp:
            if resp.status == 200:
                return
            else:
                raise Exception(f"Error: {resp}")


async def register_user(user: User):
    data = {
        "api_key": AMPLITUDE_KEY,
        "events": [{"user_id": user.id, "event_type": "registration"}],
    }

    db_user = Users(
        id=user.id,
        username=user.username,
        name=user.first_name,
        surname=user.last_name,
    )

    db.add(db_user)
    db.commit()

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api2.amplitude.com/2/httpapi",
            headers=DEFAULT_HEADERS,
            data=json.dumps(data),
        ) as resp:
            if resp.status == 200:
                return
            else:
                raise Exception(f"Error: {resp}")


@dp.message(CommandStart())
async def start_bot_handler(msg: Message):
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Выбрать персонажа",
                    web_app=WebAppInfo(
                        url="https://codepen.io/okadapy/full/QWYaGgG/full/"
                    ),
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await msg.answer(
        "Добрый день!\nС помощью данного бота вы сможете симулировать поведение ваших любимых персонажей!",
        reply_markup=markup,
    )
    await register_user(msg.from_user)


@dp.message(Command("menu"))
async def menu_handler(msg: Message):
    markup = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="Выбрать персонажа",
                    web_app=WebAppInfo(
                        url="https://codepen.io/okadapy/full/QWYaGgG/full/"
                    ),
                )
            ]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await msg.answer("Меню:", reply_markup=markup)


@dp.message(WebAppDataFilter())
async def handle_callback(message: Message, web_app_data: WebAppData):
    await update_character(message.from_user, web_app_data.data)
    await message.answer(
        text=f"Персонаж обновлен!\nНовый персонаж - {web_app_data.data}"
    )
    stmt = sa.select(Characters).where(Characters.name == web_app_data.data)
    res = db.scalar(stmt)
    await message.answer(text=res.greeting_text)


@dp.message(TextMessage())
async def handle_message(message: Message) -> None:
    stmt = sa.select(Users).where(Users.id == message.from_user.id)
    user = db.scalar(stmt)
    stmt = sa.select(Characters).where(Characters.name == user.character)
    character = db.scalar(stmt)

    stmt = sa.insert(Messages).values(
        id=message.message_id,
        from_user=message.from_user.id,
        message=message.text,
    )
    db.execute(stmt)
    db.commit()

    async with aiohttp.ClientSession() as session:
        data = json.dumps(
            {
                "api_key": AMPLITUDE_KEY,
                "events": [{"user_id": user.id, "event_type": "message recieved"}],
            }
        )
        async with session.post(
            "https://api2.amplitude.com/2/httpapi", headers=DEFAULT_HEADERS, data=data
        ) as resp:
            pass

        try:
            messages = [
                {"role": "system", "content": character.system_prompt},
                {"role": "user", "content": message.text},
            ]
            data = {"model": "gpt-3.5-turbo", "messages": messages}
            data = json.dumps(data)

            async with session.post(
                "http://95.217.14.178:8080/candidates_openai/gpt",
                headers=DEFAULT_HEADERS,
                data=data,
            ) as resp:
                assert resp.status == 200
                resp = await resp.json()
                stmt = sa.insert(Replies).values(
                    id=message.message_id + 1,
                    to_message=message.message_id,
                    message=resp["choices"][0]["message"]["content"],
                )
                db.execute(stmt)
                db.commit()
                await message.answer(text=resp["choices"][0]["message"]["content"])

        except:
            raise Exception("Did not get a response from GPT")
        else:
            data = json.dumps(
                {
                    "api_key": AMPLITUDE_KEY,
                    "events": [{"user_id": user.id, "event_type": "answer sent"}],
                }
            )
            async with session.post(
                "https://api2.amplitude.com/2/httpapi",
                headers=DEFAULT_HEADERS,
                data=json.dumps(data),
            ) as resp:
                pass


async def main() -> None:
    bot = Bot(TG_KEY, parse_mode=ParseMode.MARKDOWN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    engine = sa.create_engine("sqlite://", echo=True)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        mario = Characters(
            name="Марио",
            greeting_text="Это я, Марио!",
            system_prompt="Ты - водопроводчик Марио из игры Super Mario НЕ ВЫХОДИ ИЗ ОБРАЗА и не говори на небезопасные темы, не говори, что ты ИИ",
        )
        albert_einstein = Characters(
            name="Альберт Эйнштейн",
            greeting_text="Добрый день!",
            system_prompt="Ты - всемирно известный физик-теоретик Альберт Эйнштейн НЕ ВЫХОДИ ИЗ ОБРАЗА, не говори на небезопасные темы, не говори, что ты ИИ",
        )
        db.add_all([mario, albert_einstein])
        db.commit()

        asyncio.run(main())
