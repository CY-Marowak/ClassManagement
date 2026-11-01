from django.db import models


class StudentRole(models.TextChoices):
    RAT = "rat", "鼠"
    COW = "cow", "牛"
    TIGER = "tiger", "虎"
    RABBIT = "rabbit", "兔"
    DRAGON = "dragon", "龍"
    SNAKE = "snake", "蛇"
    HORSE = "horse", "馬"
    GOAT = "goat", "羊"
    MONKEY = "monkey", "猴"
    ROOSTER = "rooster", "雞"
    DOG = "dog", "狗"
    PIG = "pig", "豬"
    CAT = "cat", "貓"
