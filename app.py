from flask import Flask, render_template, request, redirect, url_for, session, send_file
import json
from collections import defaultdict
import csv
import io

# Создание экземпляра Flask приложения
app = Flask(__name__)

# Установка секретного ключа для сессий
app.secret_key = '123'

# Функция для загрузки книг из JSON файла
def load_books(file_path):
    with open(file_path, 'r', encoding='utf-8') as file:
        books = json.load(file)
    # Приведение жанров к нижнему регистру и удаление лишних пробелов
    for book in books:
        book['genre'] = [g.strip().lower() for g in book['genre']]
    return books

# Модуль обработки предпочтений пользователя
def process_preferences(genres, authors, keywords):
    preferences = defaultdict(int)
    # Приведение жанров, авторов и ключевых слов к нижнему регистру и удаление лишних пробелов
    unique_genres = set(genre.lower().strip() for genre in genres)
    unique_authors = set(author.lower().strip() for author in authors)
    unique_keywords = set(keyword.lower().strip() for keyword in keywords)

    # Подсчет предпочтений по жанрам, авторам и ключевым словам
    for genre in unique_genres:
        preferences[('genre', genre)] += 1
    for author in unique_authors:
        preferences[('author', author)] += 1
    for keyword in unique_keywords:
        preferences[('keyword', keyword)] += 1
    return preferences

# Модуль рекомендаций: расчет релевантности книги на основе предпочтений
def calculate_relevance_score(book, preferences):
    score = 0
    for key, value in preferences.items():
        if key[0] == 'genre' and key[1] in book['genre']:
            score += value * 2  # Вес жанра
        if key[0] == 'author' and key[1] == book['author']:
            score += value * 3  # Вес автора
        if key[0] == 'keyword' and key[1] in book['description']:
            score += value * 1  # Вес ключевого слова
    return score

# Фильтрация книг на основе предпочтений и дополнительных параметров
def filter_books(books, preferences, genres=None, year_filter=None, only_selected_genres=False):
    if genres is None:
        genres = []
    filtered_books = []
    for book in books:
        # Фильтрация по году издания
        if year_filter and book['year'] < year_filter:
            continue
        # Фильтрация по жанрам
        if genres:
            book_genres = set(book['genre'])
            selected_genres = set(genres)
            if only_selected_genres:
                if book_genres != selected_genres:
                    continue
            else:
                if not book_genres.intersection(selected_genres):
                    continue
        # Расчет релевантности книги
        score = calculate_relevance_score(book, preferences)
        if score > 0:
            filtered_books.append((book, score))
    return filtered_books

# Сортировка книг по заданному критерию
def sort_books(filtered_books, sort_by='score'):
    if sort_by == 'rating':
        sort_key = lambda x: x[1]
    elif sort_by == 'title':
        sort_key = lambda x: x[0]['title']
    elif sort_by == 'year':
        sort_key = lambda x: x[0]['year']
    else:
        raise ValueError("Invalid sort_by value")
    reverse = sort_by in ['rating', 'year']
    return sorted(filtered_books, key=sort_key, reverse=reverse)

# Загрузка книг из файла
books = load_books('books.json')

# Главная страница
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Получение данных из формы
        genres_input = request.form.get('genres', '')
        genres = [g.strip().lower() for g in genres_input.split(',') if g.strip()]
        authors = [a.strip().lower() for a in request.form.getlist('authors')]
        keywords = [k.strip().lower() for k in request.form.getlist('keywords')]
        year_filter = request.form.get('year_filter')
        only_selected_genres = request.form.get('only_selected_genres') is not None  # Преобразование в булево значение
        sort_by = request.form.get('sort_by')

        # Обработка предпочтений
        preferences = process_preferences(genres, authors, keywords)
        # Фильтрация книг
        filtered_books = filter_books(
            books,
            preferences,
            genres,
            year_filter=int(year_filter) if year_filter else None,
            only_selected_genres=only_selected_genres
        )
        # Сортировка книг
        sorted_books = sort_books(filtered_books, sort_by=sort_by)

        # Присвоение рейтинга на основе ранга
        session_books = []
        for i, (book, score) in enumerate(sorted_books, start=1):
            session_books.append({
                'title': book['title'],
                'author': book['author'],
                'genre': book['genre'],
                'year': book['year'],
                'rating': i,  # Рейтинг на основе ранга
                'added_to_read_list': book['title'] in session.get('read_list', []),
                'score': score
            })
        session['recommendations'] = session_books  # Сохранение в сессии
        return redirect(url_for('recommendations'))
    return render_template('index.html')

# Страница с рекомендациями
@app.route('/recommendations')
def recommendations():
    if 'recommendations' not in session:
        return redirect(url_for('index'))
    # Обновление флага 'added_to_read_list' на основе 'read_list'
    read_list = session.get('read_list', [])
    for book in session['recommendations']:
        book['added_to_read_list'] = book['title'] in read_list
    return render_template('recommendations.html', books=session['recommendations'])

# Добавление книги в список для чтения
@app.route('/add_to_read_list', methods=['POST'])
def add_to_read_list():
    book_title = request.form.get('book_title')
    if 'read_list' not in session:
        session['read_list'] = []
    if book_title not in session['read_list']:
        session['read_list'].append(book_title)
        # Обновление флага 'added_to_read_list' в рекомендациях
        for book in session['recommendations']:
            if book['title'] == book_title:
                book['added_to_read_list'] = True
                break
    session.modified = True  # Убеждаемся, что сессия сохранена
    return redirect(url_for('recommendations'))

# Удаление книги из списка для чтения
@app.route('/remove_from_read_list', methods=['POST'])
def remove_from_read_list():
    book_title = request.form.get('book_title')
    if 'read_list' in session and book_title in session['read_list']:
        session['read_list'].remove(book_title)
        # Обновление флага 'added_to_read_list' в рекомендациях
        for book in session['recommendations']:
            if book['title'] == book_title:
                book['added_to_read_list'] = False
                break
    session.modified = True  # Убеждаемся, что сессия сохранена
    return redirect(url_for('recommendations'))

# Сохранение рекомендаций в файл
@app.route('/save_recommendations', methods=['POST'])
def save_recommendations():
    if 'recommendations' not in session:
        return "Нет рекомендаций для сохранения", 400
    recommendations = session['recommendations']
    # Обновление флага 'added_to_read_list' на основе 'read_list'
    read_list = session.get('read_list', [])
    for book in recommendations:
        book['added_to_read_list'] = book['title'] in read_list
    file_format = request.form.get('file_format')
    if file_format == 'csv':
        response = save_to_csv(recommendations)
    elif file_format == 'json':
        response = save_to_json(recommendations)
    else:
        return "Неподдерживаемый формат файла", 400
    return response

# Сохранение рекомендаций в CSV
def save_to_csv(recommendations):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Название', 'Автор', 'Жанр', 'Год', 'Рейтинг', 'Добавлено в список для прочтения'])
    for book in recommendations:
        writer.writerow([
            book['title'],
            book['author'],
            ', '.join(book['genre']),
            book['year'],
            book['rating'],
            'True' if book['added_to_read_list'] else 'False'
        ])
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='recommendations.csv'
    )

# Сохранение рекомендаций в JSON
def save_to_json(recommendations):
    return send_file(
        io.BytesIO(json.dumps(recommendations, ensure_ascii=False).encode('utf-8')),
        mimetype='application/json',
        as_attachment=True,
        download_name='recommendations.json'
    )

# Запуск приложения
if __name__ == '__main__':
    app.run(debug=True)