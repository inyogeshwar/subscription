import time
import telebot

user_cooldowns = {}

def rate_limit(seconds=2):
    """
    Prevents callback spamming and request overloads on database
    """
    def decorator(func):
        def wrapper(message, *args, **kwargs):
            if isinstance(message, telebot.types.Message):
                user_id = message.from_user.id
            elif isinstance(message, telebot.types.CallbackQuery):
                user_id = message.from_user.id
            else:
                return func(message, *args, **kwargs)

            now = time.time()
            if user_id in user_cooldowns:
                elapsed = now - user_cooldowns[user_id]
                if elapsed < seconds:
                    return
            user_cooldowns[user_id] = now
            return func(message, *args, **kwargs)
        return wrapper
    return decorator
