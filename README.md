# Univer Thesis — Django + PostgreSQL

**2-СӨЖ:** «Django негізінде дерекқормен жұмыс істейтін CRUD веб-қосымшасын әзірлеу».

**Пәндік сала:** университеттегі дипломдық жұмыс тақырыбын таңдау жүйесі.
Студент ғылыми жетекші мен тақырып таңдайды, оқытушы тақырып ұсынады және студенттердің
жұмыс барысын қадағалайды, әкімші барлық өтінімдерді бекітеді.

| Технология | Қолданылуы |
|---|---|
| Django 5.1 | веб-қосымша, ORM, CBV, формалар, аутентификация, admin |
| PostgreSQL | дерекқор (pgAdmin арқылы басқарылады) |
| Django REST Framework | қосымша: JSON API (`/api/`) |

---

## 1. Орнату және іске қосу

### 1.1 Дерекқор (pgAdmin)
pgAdmin → **Databases → Create → Database…** → атауы `thesis_db` → **Save**.

### 1.2 Құпия мәндер — `.env`
Құпия сөздер кодта сақталмайды. Үлгіні көшіріп, мәндерін толтырыңыз:
```bash
copy .env.example .env
```
```ini
DJANGO_SECRET_KEY=ұзын-кездейсоқ-жол
DB_NAME=thesis_db
DB_USER=postgres
DB_PASSWORD=PostgreSQL-құпия-сөзіңіз
DB_HOST=localhost
DB_PORT=5432
```
`.env` файлы `.gitignore` арқылы Git-ке жіберілмейді.

### 1.3 Іске қосу (PowerShell, жоба папкасында)
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python manage.py migrate        # кестелерді PostgreSQL-да жасайды
python manage.py seed_demo      # демо-аккаунттар мен деректер
python manage.py runserver
```
Браузерде: **http://127.0.0.1:8000/**

---

## 2. Демо-аккаунттар (құпия сөз: `beibit123`)

| Рөлі | Логиндер |
|---|---|
| Әкімші | `admin` (Django admin-ге де кіре алады: `/admin/`) |
| Оқытушылар | `talgar`, `sholpan`, `nurlan`, `aigul`, `yerlan` |
| Студенттер | `beibit` (жаңа), `ansar`, `alikhan`, `yerasyl`, `tomiris` (тақырыбы бекітілген), `dana`, `arman`, `aruzhan`, `beibit1` (жетекші өтінімі қаралуда), `nursultan`, `zhanerke` (тақырып өтінімі қаралуда), `madiyar` (өтінімі қабылданбаған) |

`python manage.py seed_demo` демо-деректерді бастапқы күйге қайтарады.

---

## 3. Модельдер (`thesis/models.py`)

8 модель (талап — кемінде 3):

| Модель | Байланыстар |
|---|---|
| `Teacher` | `user` → `User` (OneToOne) |
| `Student` | `user` (OneToOne), `teacher` → `Teacher` (**FK**), `topic` → `Topic` (OneToOne) |
| `Topic` | `teacher` → `Teacher` (**FK**), `tags` ↔ `Tag` (**ManyToMany**) |
| `Tag` | `topics` ↔ `Topic` (ManyToMany, кері байланыс) |
| `SupervisorRequest` | `student` (FK), `teacher` (FK) |
| `Application` | `student` (FK), `topic` (FK) |
| `ProgressFile` | `student` (FK), `topic` (FK), `FileField` |

- **Миграциялар:** `thesis/migrations/0001_initial.py`, `0002_tags_and_unique_title.py`.
- **Шектеу:** `UniqueConstraint(teacher, title)` — бір оқытушыда бірдей атаулы тақырып болмайды.
- **Django admin:** барлық модельдер тіркелген (`thesis/admin.py`): іздеу, сүзгілер,
  `filter_horizontal` (тегтер), `list_select_related` (N+1 жоқ).

---

## 4. Веб-CRUD — класқа негізделген көріністер (`thesis/views_crud.py`)

| Әрекет | CBV | URL |
|---|---|---|
| Тізім | `TopicListView` | `/topics/` |
| Толық бет | `TopicDetailView` | `/topics/<id>/` |
| Құру | `TopicCreateView` | `/topics/new/` |
| Өңдеу | `TopicUpdateView` | `/topics/<id>/edit/` |
| Өшіру | `TopicDeleteView` | `/topics/<id>/delete/` (растау беті) |
| Оқытушының толық беті | `TeacherDetailView` | `/teachers/<id>/` |

- **Іздеу:** атауы / сипаттамасы / оқытушы аты бойынша (`?q=`).
- **Сүзу:** оқытушы, статус, тег бойынша (`?teacher=`, `?status=`, `?tag=`).
- **Сұрыптау:** жаңа / ескі / атауы / өтінімдер саны / оқытушы (`?sort=`).
- **Беттеу:** 9 тақырыптан (`paginate_by = 9`).
- **Рұқсаттар:** `LoginRequiredMixin`, `UserPassesTestMixin` — студент тек көреді;
  оқытушы өз тақырыбын (студент алмаған болса) өзгертеді; әкімші барлығын.
- **Валидация** (`TopicCrudForm`, серверде): атауы ≥ 10 таңба және тек сандар емес;
  сипаттама ≥ 20 таңба; ең көбі 5 тег; оқытушыда атау қайталанбайды (регистрге тәуелсіз).

Сонымен қатар әкімші панелінде (`/panel/`) барлық кестелер үшін CRUD бар
(`ModelForm`: оқытушылар, студенттер, тақырыптар).

Жүйенің негізгі жұмыс ағыны: студент → жетекшіге өтінім → **оқытушы + әкімші** бекітеді →
тақырып таңдау / өз тақырыбын ұсыну → **оқытушы + әкімші** бекітеді → жұмыс барысын жүктеу.

---

## 5. ORM сапасы

| Әдіс | Қайда |
|---|---|
| **Сүзу** — `filter(Q(...) \| Q(...))` | каталог іздеуі, рөлге қарай көріну (`visible_topics`) |
| **Сұрыптау** — `order_by(...)` | каталог (`SORTS`), әкімші кестелері |
| **Агрегаттау** — `aggregate(Count(..., filter=Q(...)))` | каталог статистикасы бір сұраныспен |
| **Annotate** — `annotate(Count(...))` | өтінімдер саны, CS квотасы, тегтер саны |
| **`select_related`** (FK / OneToOne → JOIN) | барлық тізімдер, admin, API |
| **`prefetch_related` / `Prefetch`** (M2M, кері FK) | тегтер, файлдар, ашық өтінімдер |

**N+1 жоқ** — бұл тесттермен дәлелденген (`QueryCountTests`): жазбалар саны өскенде
беттегі SQL-сұраныстар саны өзгермейді.

---

## 6. Тесттер
```bash
python manage.py test thesis
```
**34 тест:**

| Топ | Не тексеріледі |
|---|---|
| `ModelTests` | модель әдістері, CS квотасы, M2M тегтер, `UniqueConstraint` |
| `WorkflowTests` | екі сатылы бекіту, квота, рұқсаттар (бизнес-логика) |
| `TopicCrudTests` | CBV: тізім/іздеу/сүзу/сұрыптау/беттеу, толық бет, құру/өңдеу/өшіру, валидация, рұқсаттар |
| `WebTests` | барлық беттер, кіру/тіркелу, файл жүктеу, әкімші CRUD, CSRF |
| `QueryCountTests` | N+1 жоқ: сұраныстар саны тұрақты |
| `ApiTests` | REST API (қосымша) |

---

## 7. Жоба құрылымы
```
config/                 баптаулар (.env оқиды), басты URL-дер
thesis/
  models.py             модельдер (FK, M2M, шектеулер)
  views_crud.py         CBV: ListView, DetailView, CreateView, UpdateView, DeleteView
  views.py              кабинеттер (студент / оқытушы / әкімші)
  services.py           бизнес-логика (екі сатылы бекіту, квота)
  forms.py              формалар және валидация
  admin.py              Django admin
  api.py                REST API (қосымша)
  management/commands/seed_demo.py   демо-деректер
  migrations/           миграциялар
  tests.py              тесттер
templates/              HTML шаблондар
static/css/app.css      дизайн
.env.example            құпия мәндер үлгісі
requirements.txt        тәуелділіктер
```

## 8. Қосымша: REST API
`/api/` — DRF интерактивті беті. Мысалы: `GET /api/topics/`, `GET /api/teachers/`
(Basic Auth: логин + құпия сөз).
