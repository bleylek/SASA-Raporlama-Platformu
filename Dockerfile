# Python 3.11 slim image
FROM python:3.11-slim

# Çalışma dizini
WORKDIR /app

# Gerekli paketleri kopyala ve yükle
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama dosyalarını kopyala
COPY . .

# Port
EXPOSE 5000

# Uygulamayı başlat
CMD ["python", "run.py"]
