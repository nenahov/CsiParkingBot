new_day_begin_hour = 19  # начало нового дня (19:00)
new_day_offset = 24 - new_day_begin_hour  # обратное смещение дня в часах (5)
new_day_queue_hour = new_day_begin_hour + 2  # начало розыгрыша мест в очереди (21:00)
new_day_auto_karma_hour = 14  # начало автоматического начисления кармы тем, кто уехал и не разыграл Карму из статуса (14:00)

quiet_hours = [1, 2, 3, 4, 5, 6]  # тихие часы (с часа до 7 утра)
timeout_before_midnight = 60  # таймаут до полуночи в минутах
timeout_after_midnight = 10  # таймаут после полуночи в минутах
