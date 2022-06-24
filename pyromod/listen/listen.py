"""
pyromod - A monkeypatcher add-on for Pyrogram
Copyright (C) 2020 Cezar H. <https://github.com/usernein>

This file is part of pyromod.

pyromod is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

pyromod is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with pyromod.  If not, see <https://www.gnu.org/licenses/>.
"""

import asyncio
import functools
import pyrogram

from ..utils import patch, patchable

loop = asyncio.get_event_loop()
    
class ListenerCanceled(Exception):
    pass
pyrogram.errors.ListenerCanceled = ListenerCanceled

@patch(pyrogram.client.Client)
class Client():
    @patchable
    def __init__(self, *args, **kwargs):
        self.listening = {}
        self.using_mod = True
        
        self.old__init__(*args, **kwargs)
    
    @patchable
    async def listen(self, chat_id, filters=None, timeout=None, require_reply=False, force_reply_id=None, force_sender=False, force_sender_id=None):
        if type(chat_id) != int:
            chat = await self.get_chat(chat_id)
            chat_id = chat.id
        
        future = loop.create_future()
        future.add_done_callback(
            functools.partial(self.clear_listener, chat_id)
        )
        update_dict = {chat_id: {"future": future, "filters": filters}}
        if require_reply:
            update_dict["req_reply"] = True
            update_dict["req_rep_id"] = force_reply_id
        if force_sender:
            update_dict["req_sndr"] = True
            update_dict["req_sndr_id"] = force_sender_id
        self.listening.update(update_dict)
        return await asyncio.wait_for(future, timeout)
    
    @patchable
    async def ask(self, chat_id, text, filters=None, timeout=None, require_reply=False, force_sender=False, force_sender_id=None, *args, **kwargs):
        request = await self.send_message(chat_id, text, *args, **kwargs)
        response = await self.listen(chat_id, filters, timeout, require_reply, request.id, force_sender, force_sender_id)
        response.request = request
        return response
   
    @patchable
    def clear_listener(self, chat_id, future):
        if future == self.listening[chat_id]["future"]:
            self.listening.pop(chat_id, None)
     
    @patchable
    def cancel_listener(self, chat_id):
        listener = self.listening.get(chat_id)
        if not listener or listener['future'].done():
            return
        
        listener['future'].set_exception(ListenerCanceled())
        self.clear_listener(chat_id, listener['future'])
        
@patch(pyrogram.handlers.message_handler.MessageHandler)
class MessageHandler():
    @patchable
    def __init__(self, callback: callable, filters=None):
        self.user_callback = callback
        self.old__init__(self.resolve_listener, filters)
    
    @patchable
    async def resolve_listener(self, client, message, *args):
        listener = client.listening.get(message.chat.id)
        if listener and not listener['future'].done():
            if listener.get('req_reply', False):
                if not message.reply_to_message:
                    return
                if listener['req_rep_id'] != message.reply_to_message.id:
                    return
            if listener.get('req_sndr', False):
                if listener['req_sndr_id'] != message.from_user.id:
                    return
            listener['future'].set_result(message)
        else:
            if listener and listener['future'].done():
                client.clear_listener(message.chat.id, listener['future'])
            await self.user_callback(client, message, *args)
    
    @patchable
    async def check(self, client, update):
        listener = client.listening.get(update.chat.id)
        
        if listener and not listener['future'].done():
            return await listener['filters'](client, update) if callable(listener['filters']) else True
            
        return (
            await self.filters(client, update)
            if callable(self.filters)
            else True
        )

@patch(pyrogram.types.user_and_chats.chat.Chat)
class Chat(pyrogram.types.Chat):
    @patchable
    def listen(self, *args, **kwargs):
        return self._client.listen(self.id, *args, **kwargs)
    @patchable
    def ask(self, *args, **kwargs):
        return self._client.ask(self.id, *args, **kwargs)
    @patchable
    def cancel_listener(self):
        return self._client.cancel_listener(self.id)

@patch(pyrogram.types.user_and_chats.user.User)
class User(pyrogram.types.User):
    @patchable
    def listen(self, *args, **kwargs):
        return self._client.listen(self.id, *args, **kwargs)
    @patchable
    def ask(self, *args, **kwargs):
        return self._client.ask(self.id, *args, **kwargs)
    @patchable
    def cancel_listener(self):
        return self._client.cancel_listener(self.id)
