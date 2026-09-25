# BI Publisher's core jars were built for Java 8, so build and run on Temurin 8.
FROM eclipse-temurin:8-jdk AS build
WORKDIR /src
COPY vendor/ /vendor/
COPY src/ /src/
RUN mkdir -p /out && javac -cp "/vendor/*" -d /out BipReportServer.java

FROM eclipse-temurin:8-jre
WORKDIR /app
COPY vendor/ /app/vendor/
COPY --from=build /out/ /app/classes/
COPY template/ /app/template/
RUN useradd -r -s /usr/sbin/nologin bip
USER bip
EXPOSE 8790
CMD ["java", "-Djava.awt.headless=true", "-Xmx512m", "-cp", "/app/classes:/app/vendor/*", "BipReportServer"]
