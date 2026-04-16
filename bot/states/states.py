from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    choosing_language = State()      # Выбор казахский/английский
    showing_intro = State()          # Приветственное сообщение
    placement_test = State()         # Placement test
    placement_result = State()       # Показываем результат


class LessonStates(StatesGroup):
    in_lesson = State()              # Идёт урок
    waiting_text_answer = State()    # Ждём текстовый ответ
    waiting_voice_answer = State()   # Ждём голосовой ответ
    lesson_complete = State()        # Урок завершён


class ReviewStates(StatesGroup):
    in_review = State()              # Режим повторения
    rating_card = State()            # Оцениваем карточку


class SettingsStates(StatesGroup):
    main = State()
    changing_notify_time = State()
