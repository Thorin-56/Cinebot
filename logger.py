import os
import datetime


class Logger:
    def __init__(self):
        self.dir_path = "./logs"
        self.__struct_name_file = "logs-{D}_{M}_{Y}-{id}.log"
        self.file_name = self.__get_last_file_name()

    def __get_last_file_name(self):
        today = datetime.date.today().strftime("%d %m %Y").split()
        files = [*filter(lambda x: x[:-8] == self.__struct_name_file[:-9].format(**(dict(zip(("D", "M", "Y"), today)))),
                       os.listdir(self.dir_path))]
        if files:
            return self.__struct_name_file.format(**(dict(zip(
                ("D", "M", "Y"), today))), id=f"{int(sorted(files, key=lambda x: int(x[-7:-4]))[-1][-7:-4]) + 1:0>3}")
        else:
            return self.__struct_name_file.format(**(dict(
                zip(("D", "M", "Y"), today))), id="001")

    def log(self, content):
        with open(f"{self.dir_path}/{self.file_name}", "a", encoding="utf-8") as file:
            data = f"[{datetime.datetime.today().strftime("%d/%m/%Y %H:%M:%S")}] {content}"
            file.write(data + "\n")
            print(data, flush=True)


if __name__ == '__main__':
    a = Logger()
    a.log("Coucou")
    a.log("Coucou1")
    a.log("Coucou2")
    a.log("Coucou3")
