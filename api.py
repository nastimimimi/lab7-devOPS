import os
import random
import copy
from typing import List, Dict
from flask import Flask, request, jsonify

app = Flask(__name__)

DEBUG_MODE = os.environ.get('DEBUG', 'false').lower() == 'true'
PORT       = int(os.environ.get('PORT', 5000))
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')

app.config['SECRET_KEY'] = SECRET_KEY
app.config['DEBUG']      = DEBUG_MODE


class InputData:
    def __init__(self, teachers_count=15, courses_count=30,
                 rooms_count=12, groups_count=10):
        self.teachers_count = teachers_count
        self.courses_count  = courses_count
        self.rooms_count    = rooms_count
        self.groups_count   = groups_count
        self.days_count     = 5
        self.pairs_per_day  = 6
        self.slots_total    = self.days_count * self.pairs_per_day

        self.teachers = self._init_teachers()
        self.courses  = self._init_courses()
        self.rooms    = self._init_rooms()
        self.groups   = self._init_groups()

    def _init_teachers(self):
        return [{'id': i, 'name': f'Викладач_{i+1}',
                 'preferred': random.sample(
                     range(self.slots_total), random.randint(5, 15))}
                for i in range(self.teachers_count)]

    def _init_courses(self):
        kinds = ['Лекція', 'Практика', 'Лабораторна']
        return [{'id': i, 'name': f'Дисципліна_{i+1}',
                 'kind':       random.choice(kinds),
                 'teacher_id': random.randint(0, self.teachers_count - 1),
                 'group_id':   random.randint(0, self.groups_count - 1)}
                for i in range(self.courses_count)]

    def _init_rooms(self):
        kinds = ["Лекційна", "Комп'ютерна", 'Лабораторія']
        return [{'id': i, 'name': f'Ауд_{100+i}',
                 'seats': random.randint(20, 50),
                 'kind':  random.choice(kinds)}
                for i in range(self.rooms_count)]

    def _init_groups(self):
        return [{'id': i, 'name': f'Група_{i+1}',
                 'size': random.randint(15, 30)}
                for i in range(self.groups_count)]


class GeneticScheduler:
    def __init__(self, data: InputData, pop_size=50,
                 max_generations=200, mutation_prob=0.1):
        self.data            = data
        self.w_conflicts     = 1000
        self.w_gaps          = 10
        self.w_preferences   = 1
        self.pop_size        = pop_size
        self.max_generations = max_generations
        self.mutation_prob   = mutation_prob
        self.log: List[Dict] = []

    def _random_individual(self):
        return [{'course_id':    c['id'],
                 'course_name':  c['name'],
                 'teacher_id':   c['teacher_id'],
                 'teacher_name': self.data.teachers[c['teacher_id']]['name'],
                 'group_id':     c['group_id'],
                 'group_name':   self.data.groups[c['group_id']]['name'],
                 'room_id':      random.randint(0, self.data.rooms_count - 1),
                 'slot':         random.randint(0, self.data.slots_total - 1),
                 'kind':         c['kind']}
                for c in self.data.courses]

    def _count_conflicts(self, individual):
        total = 0
        for slot in range(self.data.slots_total):
            for key in ('teacher_id', 'room_id', 'group_id'):
                vals = [e[key] for e in individual if e['slot'] == slot]
                total += len(vals) - len(set(vals))
        for tid in range(self.data.teachers_count):
            for day in range(self.data.days_count):
                s = day * self.data.pairs_per_day
                e = s + self.data.pairs_per_day
                day_cl = [x for x in individual
                          if x['teacher_id'] == tid and s <= x['slot'] < e]
                if len(day_cl) > 4:
                    total += len(day_cl) - 4
        return total

    def _count_gaps(self, individual):
        gaps = 0
        for tid in range(self.data.teachers_count):
            for day in range(self.data.days_count):
                s = day * self.data.pairs_per_day
                e = s + self.data.pairs_per_day
                slots = sorted([x['slot'] for x in individual
                                if x['teacher_id'] == tid and s <= x['slot'] < e])
                for i in range(len(slots) - 1):
                    gaps += max(0, slots[i+1] - slots[i] - 1)
        return gaps

    def _count_pref_deviation(self, individual):
        total = 0
        for entry in individual:
            pref = self.data.teachers[entry['teacher_id']]['preferred']
            if entry['slot'] not in pref:
                total += min(abs(entry['slot'] - p) for p in pref)
        return total

    def _fitness(self, individual):
        return (self.w_conflicts   * self._count_conflicts(individual) +
                self.w_gaps        * self._count_gaps(individual) +
                self.w_preferences * self._count_pref_deviation(individual))

    def run(self):
        population = [self._random_individual() for _ in range(self.pop_size)]
        best       = min(population, key=self._fitness)
        best_score = self._fitness(best)

        for gen in range(self.max_generations):
            scores   = [self._fitness(ind) for ind in population]
            selected = []
            for _ in range(len(population) // 2):
                candidates = random.sample(list(zip(population, scores)), 3)
                selected.append(copy.deepcopy(min(candidates, key=lambda x: x[1])[0]))

            new_pop = []
            for i in range(0, len(selected) - 1, 2):
                pt = random.randint(1, len(selected[i]) - 1)
                c1 = selected[i][:pt] + selected[i+1][pt:]
                c2 = selected[i+1][:pt] + selected[i][pt:]
                for c in (c1, c2):
                    if random.random() < self.mutation_prob:
                        a, b = random.sample(range(len(c)), 2)
                        c[a]['slot'], c[b]['slot'] = c[b]['slot'], c[a]['slot']
                new_pop.extend([c1, c2])

            population = sorted(new_pop + selected,
                                 key=self._fitness)[:self.pop_size]
            cur = self._fitness(population[0])
            if cur < best_score:
                best_score = cur
                best = copy.deepcopy(population[0])

            self.log.append({'generation': gen,
                             'best_score': best_score,
                             'conflicts':  self._count_conflicts(best)})
        return best


@app.route('/calculate', methods=['POST'])
def calculate():
    body = request.get_json(silent=True) or {}

    def to_int(v, d, lo, hi):
        try:    return max(lo, min(hi, int(v)))
        except: return d

    def to_float(v, d, lo, hi):
        try:    return max(lo, min(hi, float(v)))
        except: return d

    teachers_count  = to_int(body.get('teachers_count'),   15,  2,  50)
    courses_count   = to_int(body.get('courses_count'),    30,  2, 100)
    rooms_count     = to_int(body.get('rooms_count'),      12,  2,  40)
    groups_count    = to_int(body.get('groups_count'),     10,  2,  30)
    pop_size        = to_int(body.get('pop_size'),         50, 10, 200)
    max_generations = to_int(body.get('max_generations'), 100,  1, 500)
    mutation_prob   = to_float(body.get('mutation_prob'), 0.1, 0.0, 1.0)

    data      = InputData(teachers_count, courses_count, rooms_count, groups_count)
    scheduler = GeneticScheduler(data, pop_size, max_generations, mutation_prob)
    result    = scheduler.run()

    conflicts = scheduler._count_conflicts(result)
    gaps      = scheduler._count_gaps(result)
    pref_dev  = scheduler._count_pref_deviation(result)
    score     = scheduler._fitness(result)

    day_names = ['Понеділок', 'Вівторок', 'Середа', 'Четвер', "П'ятниця"]
    preview = []
    for item in result[:5]:
        room = data.rooms[item['room_id']]
        preview.append({
            'course':   item['course_name'],
            'kind':     item['kind'],
            'teacher':  item['teacher_name'],
            'group':    item['group_name'],
            'room':     room['name'],
            'day':      day_names[item['slot'] // data.pairs_per_day],
            'pair':     item['slot'] % data.pairs_per_day + 1
        })

    return jsonify({
        "status": "success",
        "input":  {"teachers_count":  teachers_count,
                   "courses_count":   courses_count,
                   "rooms_count":     rooms_count,
                   "groups_count":    groups_count,
                   "pop_size":        pop_size,
                   "max_generations": max_generations,
                   "mutation_prob":   mutation_prob},
        "result": {"conflicts":       conflicts,
                   "gaps":            gaps,
                   "pref_deviation":  pref_dev,
                   "final_score":     round(score, 2),
                   "iterations_done": len(scheduler.log),
                   "schedule_size":   len(result),
                   "schedule_preview": preview}
    })


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "model":  "Genetic Algorithm — Schedule Optimizer",
        "author": "Баранова Анастасія, АІ-231",
        "debug":  DEBUG_MODE
    })


@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "service":   "Schedule Optimizer API",
        "version":   "1.0",
        "endpoints": [
            "POST /calculate",
            "GET  /health"
        ]
    })


if __name__ == '__main__':
    print("=" * 50)
    print(f" Сервер запущено на порту {PORT}")
    print(f" Debug mode: {DEBUG_MODE}")
    print(" POST /calculate")
    print(" GET  /health")
    print("=" * 50)
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG_MODE)
