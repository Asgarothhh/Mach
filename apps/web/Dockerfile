FROM nginx:alpine

# Создаем тестовую заглушку, пока Разработчик 4 не напишет Frontend
RUN echo "<h1>MTS Voice Agent - API is Running</h1><p>Frontend will be available here.</p>" > /usr/share/nginx/html/index.html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]