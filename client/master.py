from tkinter import *
from tkinter.ttk import *
from threading import Thread, enumerate, active_count
import time
from winsound import PlaySound, SND_LOOP, SND_ASYNC, SND_PURGE
from client.gui_methods import center_window, pop_up_message
from client import ask_server
from client.chat_client import ChatClient


# creates the pages and shows them
class App(Tk):
    start_page_background = r"..\media\bg_pic.png"

    def __init__(self, *args, **kwargs):
        Tk.__init__(self, *args, **kwargs)
        self.title('VoiceChat')
        # Setup Frame
        self.container = Frame(self)
        self.container.pack(side="top", fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.username = ''
        self.target = ''
        self.user_called = ''

        self.frames = {}

        self.sp_background = PhotoImage(file=App.start_page_background)

        # self.threading_state() # used for debugging
        self.create_frames()
        center_window(self)
        self.show_frame(StartPage)
        # The following three commands are needed so the window pops
        # up on top on Windows...
        self.iconify()
        self.update()
        self.deiconify()

    def create_frames(self):
        for F in (StartPage, Login, Register, Main, Calling, Called, Chat):
            frame = F(self.container, self)
            self.frames[F] = frame
            frame.grid(row=0, column=0, sticky="nsew")

    def show_frame(self, context):
        frame = self.frames[context]
        frame.tkraise()

    def threading_state(self, wait=8000):
        threads = [thread.getName() for thread in enumerate() if thread.getName() != 'MainThread']
        if threads:
            print('threads num:', active_count() - 1)
            print(threads)
        self.after(wait, self.threading_state)


# chat page
class Chat(Frame):
    def __init__(self, master, controller):
        super().__init__(master)
        self.controller = controller
        self.msg = Label(self, font=('Ariel', 20), foreground='green')
        self.msg.pack()
        Button(self, text='End Chat', command=self.stop_chat).pack()

    def stop_chat(self):
        ask_server.stop(self.controller.username, 'call')

    def start_chat(self):
        user = self.controller.target
        if not user:
            user = self.controller.user_called
        self.msg['text'] = f'In chat with {user}'
        self.client = ChatClient()
        Thread(target=self.chat_ended, name='chat_ended', daemon=True).start()
        self.client.start()

    def chat_ended(self):
        time.sleep(2)
        while True:
            time.sleep(1)
            if not ask_server.is_in_chat(self.controller.username):
                self.client.end()
                self.controller.show_frame(Main)
                time.sleep(0.4)
                self.controller.frames[Called].start_checking()
                break


# receiving or making a call page
class Main(Frame):
    def __init__(self, master, controller):
        super().__init__(master)
        self.users = Listbox(self, fg='green', font=('Ariel', 12))
        self.target_name = Entry(self, font=('Ariel', 12))
        self.controller = controller
        self.set()
        self.set_users_list()

    def set(self):
        Label(self, text='Call to', font=('Ariel', 20), foreground='magenta').pack(side=TOP)
        self.target_name.pack()
        Button(self, text='Call', command=self.pre_call).pack()
        Label(self, text='Users', font=('Ariel', 18), foreground='blue').pack()
        self.users.pack()
        self.users.bind('<<ListboxSelect>>', self.to_entry)
        self.bind('<Return>', self.pre_call)
        self.target_name.focus_set()

    # create list of users
    def set_users_list(self):
        self.users.delete(0, END)
        users = ask_server.user_lists()
        for user in users:
            if user != self.controller.username:
                self.users.insert(END, user)
        if self.users.size() < 10:
            self.users.configure(height=self.users.size())
        self.after(5000, self.set_users_list)

    # put a user in entry
    def to_entry(self, event=None):
        index = self.users.curselection()
        name = self.users.get(index)
        self.target_name.delete(0, END)
        self.target_name.insert(0, name)

    # checks if name valid, if so runs call
    def pre_call(self, event=None):
        target = self.target_name.get()
        self.target_name.delete(0, END)
        if len(target) > 2 and target != self.controller.username:
            if ask_server.is_user(target):  # checks if the user exists
                self.controller.target = target
                self.controller.show_frame(Calling)
                self.controller.frames[Calling].call()
            else:
                pop_up_message(f"sorry, the user '{target}' is not registered yet")
        elif len(target) < 3:
            pop_up_message('sorry, the name is too short, at least 3 characters')
        else:
            pop_up_message("you can't call yourself")


# waiting for a call to be answered page
class Calling(Frame):
    ring = r"..\media\calling_ring.wav"

    def __init__(self, master, controller):
        super().__init__(master)
        self.controller = controller
        self.cancel = False
        self.label = Label(self, font=('Ariel', 20), foreground='magenta')
        self.label.pack()
        Button(self, text='Cancel Call', command=self.stop_calling).pack()

    def call(self):
        # print(f'calling {self.controller.target}')
        self.label['text'] = f'Calling {self.controller.target}...'
        Thread(target=self.calling, name='calling', daemon=True).start()

    # cancels call
    def stop_calling(self):
        ask_server.stop(self.controller.username, 'calling')
        self.cancel = True

    # checks if target agreed to chat
    def answer(self, timeout=1):
        max_time = time.time() + 60 * timeout  # 1 minutes from now
        # check if 'calling' changed to 'call'
        PlaySound(Calling.ring, SND_LOOP + SND_ASYNC)
        while True:
            time.sleep(1)
            if self.cancel:
                result = 'canceled'
                # print(result)
                break
            if time.time() > max_time:
                result = 'timed_out'
                break
            if ask_server.is_in_chat(self.controller.username):
                result = 'accepted'
                break
            if not ask_server.not_rejected(self.controller.username, self.controller.target):
                result = 'rejected'
                break
        PlaySound(None, SND_PURGE)
        return result

    # calls and handle the call
    def calling(self):
        is_posted = ask_server.call(self.controller.username, self.controller.target)
        if is_posted:
            # print('call posted')
            result = self.answer(1)
            if result == 'accepted':
                # print('call accepted')
                self.controller.show_frame(Chat)
                self.controller.frames[Chat].start_chat()
            else:
                self.controller.show_frame(Main)
                if result == 'timed_out':  # waited too long for response from the call target
                    pop_up_message("call canceled, didn't receive answer in time")
                    # print("call canceled, didn't receive answer in time")
                elif result == 'canceled':
                    self.cancel = False
                elif result == 'rejected':
                    pop_up_message("call rejected")
                    # print("call canceled")

        else:  # error, call already exists, handling
            # print('error')
            ask_server.stop(self.controller.username, 'calling')
            self.calling()


# receiving a call page
class Called(Frame):
    ring = r"..\media\called_ring.wav"

    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        self.text1 = Label(self, font=('Ariel', 20), foreground='magenta')
        self.text1.pack()
        self.bind('<Return>', self.yes)
        yes = Button(self, text='yes', command=self.yes)
        yes.focus_set()
        yes.pack()
        Button(self, text='no', command=self.no).pack()

    def start_checking(self):
        Thread(target=self.called, name='called', daemon=True).start()

    def called(self):
        # print(f'hi {self.controller.username}, waiting for a call')
        while True:
            if ask_server.look_for_call(self.controller.username):
                self.controller.show_frame(Called)
                user = ask_server.get_src_name(self.controller.username)
                self.controller.user_called = user
                # print(f'{user} called')
                self.text1['text'] = f'you got a call from {user}\ndo you want to answer'
                PlaySound(Called.ring, SND_LOOP + SND_ASYNC)
                break
            if ask_server.is_in_chat(self.controller.username):  # when calling and call was approved
                break
            time.sleep(1)

    def yes(self):
        PlaySound(None, SND_PURGE)
        successful = ask_server.accept(self.controller.user_called, self.controller.username)
        if successful == 'True':
            time.sleep(0.5)
            self.controller.show_frame(Chat)
            self.controller.frames[Chat].start_chat()
        else:
            pop_up_message('call was canceled')
            # print('call was canceled')
            ask_server.stop(self.controller.username, 'calling')
            self.controller.show_frame(Main)
            self.start_checking()

    def no(self):
        ### is this how i wanna handle that? the caller dont check if we canceled
        PlaySound(None, SND_PURGE)
        ask_server.stop(self.controller.username, 'calling')
        self.controller.show_frame(Main)
        self.start_checking()


# front page of the app
class StartPage(Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        background_label = Label(self, image=controller.sp_background)
        background_label.place(x=0, y=0, relwidth=1, relheight=1)
        Label(self, text='Welcome to VOICECHAT, please log in to continue',
              font=('Ariel', 18), foreground='orange').pack(padx=5, pady=5)
        Button(self, text='login', command=lambda: controller.show_frame(Login)).pack()
        Label(self, text='Not registered yet? Do it now',
              font=('Ariel', 15), foreground='blue').pack(padx=5, pady=5)
        Button(self, text='register', command=lambda: controller.show_frame(Register)).pack()


# login page
class Login(Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        # Label(self, text='Login', font=('Ariel', 20), foreground='orange').grid()
        self.entry_name = Entry(self)
        self.entry_pas = Entry(self, show='*')
        name = Label(self, text='Name')
        pas = Label(self, text='Password')
        enter = Button(self, text='Enter', command=self.collect)
        self.bind('<Return>', self.collect)
        self.entry_name.focus_set()
        # grid & pack
        name.grid(row=0, sticky=E)
        pas.grid(row=1, sticky=E)
        self.entry_name.grid(row=0, column=1)
        self.entry_pas.grid(row=1, column=1)
        enter.grid()

    def enter(self, name, pas):
        is_connected = ask_server.login(name, pas)
        if is_connected:
            self.controller.username = name
            pop_up_message(f"you're in, {name}")
            self.controller.create_frames()
            self.controller.show_frame(Main)
            self.controller.frames[Called].start_checking()
        else:
            self.entry_name.delete(0, END)
            self.entry_pas.delete(0, END)
            pop_up_message("name or password is incorrect")

    def collect(self):
        name = self.entry_name.get()
        pas = self.entry_pas.get()
        self.enter(name, pas)


# register page
class Register(Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        # Label(self, text='Register', font=('Ariel', 20), foreground='blue').grid()
        self.entry_name = Entry(self)
        self.entry_password = Entry(self)
        name = Label(self, text='Name')
        pas = Label(self, text='Password')
        enter = Button(self, text='Register', command=self.handle)
        self.bind('<Return>', self.handle)
        self.entry_name.focus_set()

        # grid & pack
        name.grid(row=0, sticky=E)
        pas.grid(row=1, sticky=E)
        self.entry_name.grid(row=0, column=1)
        self.entry_password.grid(row=1, column=1)
        enter.grid()

    def handle(self, event=None):
        # acquire args
        name = self.entry_name.get()
        pas = self.entry_password.get()
        self.entry_name.delete(0, END)
        self.entry_password.delete(0, END)
        # checks if valid
        if len(name) < 3 or len(pas) < 3:
            pop_up_message('name and password must be at least 3 characters')
        # add to database unless name is already used
        else:
            success = ask_server.register(name, pas)
            if success:
                # pop_up_message('added to database')
                self.controller.frames[Login].enter(name, pas)
            else:
                pop_up_message('username already used')


if __name__ == '__main__':
    app = App()
    app.mainloop()
