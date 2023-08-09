import typer
from functools import wraps
from typing_extensions import Annotated
from passlib.context import CryptContext
from sqlalchemy.orm import Session
import os
import time
import datetime
import threading
import docker
import database

app = typer.Typer()
user_app = typer.Typer()
app.add_typer(user_app, name="user")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# client = docker.from_env()

# def get_container_ip(container_name):
#     try:
#         container = client.containers.get(container_name)
#         networks = container.attrs['NetworkSettings']['Networks']
        
#         # Assuming you're interested in the default bridge network
#         default_network = networks['bridge']
        
#         return default_network['IPAddress']
#     except docker.errors.NotFound:
#         return None

database_name = "espf_users"
#database_ip = get_container_ip(database_name)
database_ip = "172.18.0.2"
container_name = "mariadb"

#Wrapper used to check the user connexion
def login_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        username=os.getenv('username')  
        password=os.getenv('password')
        if user_authentificated(username=username,password=password):
            return function(*args, **kwargs)
        else:
            return typer.secho(f"Wrong credentials", fg=typer.colors.RED)
    return wrapper

#Function used to check the credentials on a specific route
def user_authentificated(username:str, password:str):
    if username==None or password==None:
        typer.secho(f"You need to login", fg=typer.colors.RED)
        return False
    #password = get_password_hash(password) #2nd hash of the admin password used to connect to the DB
    try: 
        global database_ip
        global database_name
        database.test_credentials(
            DB_Username_For_Admin=username,
            DB_Password_For_Admin=password,
            DB_Name_For_Users_Tables=database_name,
            DB_Container_Name=database_ip
        )   
    except:
        return False
    return True

################ ALL OF THE CLI COMMANDS ################

@app.command("login")
def login(
    username: Annotated[str, typer.Option(prompt=True)], 
    password: Annotated[str, typer.Option(prompt=True, hide_input=True)]
    ) -> None: 
    #password = get_password_hash(password)  #1st hash of the admin password stored in an env variable
    if user_authentificated(username=username, password=password):
        os.putenv('username',f'{username}')
        os.putenv('password',f'{password}')
        background_thread = threading.Thread(target=auto_logout)
        background_thread.start()
        typer.secho(f"You are now connected", fg=typer.colors.GREEN)
        return os.system('bash')
    else:
        os.putenv('username','')
        os.putenv('password','')
        typer.secho(f"Wrong credentials", fg=typer.colors.RED)
        return os.system('bash')

@app.command("logout")
def logout() -> None: 
        os.putenv('username','')
        os.putenv('password','')
        typer.secho(f"You are now disconnected", fg=typer.colors.RED)
        return os.system('bash')

@user_app.command("list")
@login_required
def user() -> None:
    session = connect_to_db()
    user_list(session=session)

@user_app.command('add')
@login_required
def user_add_command(
    username:str, 
    password: Annotated[str, typer.Option(prompt="The client password", hide_input=True)], 
    activated: Annotated[bool, typer.Argument()]=False,
    expiration_date: Annotated[str, typer.Argument()]=None
    ) -> None:
    session = connect_to_db()
    user_add(session=session, username=username, password=password, activated=activated, expirationDate=expiration_date)
        
@user_app.command("get")
@login_required
def user_get_command(username:str) -> None:
    session = connect_to_db()
    user_get(session=session, username=username)

@user_app.command("delete")
@login_required
def user_delete_command(username:str) -> None:
    session = connect_to_db()
    user_delete(session=session, username=username)

@user_app.command('update')
@login_required
def user_update_command(
    username:str, 
    newUsername:Annotated[str, typer.Option(
            "--newusername",
            "-u")
        ]=None,
    newPassword: Annotated[str, typer.Option(
            "--newpassword",
            "-pw",
            hide_input=True)
        ]=None, 
    activate: Annotated[bool, typer.Option(
            "--activate/--deactivate",
            "-a/-d")
        ]=None,
    expirationDate : Annotated[str, typer.Option(
            "--expirationdate",
            "-expd")
        ]=None
    ) -> None:
    session : Session = connect_to_db()
    user_update(session=session, username=username, newUsername = newUsername, password=newPassword, activated=activate, expirationDate=expirationDate)
        
@user_app.command('activate')
@login_required
def user_activate_command(username:str) -> None:
    session = connect_to_db()
    user_activate(session=session, username=username)

@user_app.command('deactivate')
@login_required
def user_deactivate_command(username:str) -> None:
    session = connect_to_db()
    user_deactivate(session=session, username=username)
    
@user_app.command('changedate')
@login_required
def user_update_expiration_date(
    username:str,
    expirationdate: Annotated[str, typer.Argument(help="The expiration date for the user, format: yyyy/mm/dd")]
    ) -> None:
    session = connect_to_db()
    expirationdate=convert_string_to_date(date=expirationdate)
    if expirationdate:
        user_change_expiration_date(session=session, username=username, expirationDate=expirationdate)
    else:
        typer.secho(f"Wrong format for expiration date", fg=typer.colors.RED)

################ FUNCTIONS USED TO LIGHTEN CLI COMMANDS CODE ################

def user_list(session):
    users = database.get_all_users(session)
    if len(users) == 0:
        typer.secho("There are no users in the database yet", fg=typer.colors.RED)
        raise typer.Exit()
    typer.secho("\nUser list:\n", fg=typer.colors.BLUE, bold=True)
    columns = (
        "ID.  ",
        "| Username  ",
        "| Activated  ",
        "| Expiration Date"
    )
    headers = "".join(columns)
    typer.secho(headers, fg=typer.colors.BLUE, bold=True)
    typer.secho("-" * len(headers), fg=typer.colors.BLUE)
    for id, user in enumerate(users, 1):
        username, activated, expiration = user.username, user.activated, user.expiration_date
        typer.secho(
            f"{id}{(len(columns[0]) - len(str(id))) * ' '}"
            f"| ({username}){(len(columns[1]) - len(str(username)) - 4) * ' '}"
            f"| {activated}{(len(columns[2]) - len(str(activated)) - 2) * ' '}"
            f"| {expiration}{(len(columns[2]) - len(str(expiration)) - 2) * ' '}",   
            fg=typer.colors.BLUE,
        )
    typer.secho("-" * len(headers) + "\n", fg=typer.colors.BLUE)
    return True

def user_add(session, username:str, password:str, activated:bool, expirationDate:str):
    password = get_password_hash(password)
    if expirationDate: 
        expirationDate = convert_string_to_date(expirationDate)
        if not expirationDate:
            return typer.secho(f"Wrong format for expiration date", fg=typer.colors.RED)
    if database.add_user(session=session, username=username, password=password, activated=activated, expirationDate=expirationDate):
        return typer.secho(f"User {username} was added to the database, his activated state is {activated}, his expiration date is {expirationDate}", fg=typer.colors.GREEN)
    return typer.secho(f"Unsuccesfull add of the user {username}", fg=typer.colors.RED)

def user_get(session, username:str):
    user = database.get_a_single_user(session=session, username=username)
    if not user:
        typer.secho("This user doesn't exist", fg=typer.colors.RED)
        raise typer.Exit()
    typer.secho("\nUser:\n", fg=typer.colors.BLUE, bold=True)
    columns = (
        "ID.  ",
        "| Username  ",
        "| Activated  ",
        "| Expiration Date",
    )
    headers = "".join(columns)
    typer.secho(headers, fg=typer.colors.BLUE, bold=True)
    typer.secho("-" * len(headers), fg=typer.colors.BLUE)
    id, username, activated, expiration = user.id, user.username, user.activated, user.expiration_date
    typer.secho(
        f"{id}{(len(columns[0]) - len(str(id))) * ' '}"
        f"| ({username}){(len(columns[1]) - len(str(username)) - 4) * ' '}"
        f"| {activated}{(len(columns[2]) - len(str(activated)) - 2) * ' '}"
        f"| {expiration}{(len(columns[2]) - len(str(expiration)) - 2) * ' '}",     
        fg=typer.colors.BLUE,
    )
    typer.secho("-" * len(headers) + "\n", fg=typer.colors.BLUE)
    return True

def user_delete(session, username:str):
    user = database.get_a_single_user(session=session, username=username)
    if user:
        if ask_confirmation_delete_user:
            user = database.delete_user(session=session, username=username)
            typer.secho(f"User {user.username} have been delete", fg=typer.colors.GREEN)
        else : 
            typer.secho(f"Deletion of {user.username} cancelled", fg=typer.colors.RED)
    else: 
        typer.secho("This user doesn't exist", fg=typer.colors.RED)

def user_update(session:Session, username:str, newUsername:str, password:str,  activated:bool, expirationDate:datetime.date):
    check=[]
    if newUsername:
        if database.update_user_username(session=session, username=username, newUsername=newUsername):
            typer.secho(f"User {username} is now {newUsername}", fg=typer.colors.GREEN)
        else: 
            typer.secho(f"Failure in the update of user {username} username as {newUsername}", fg=typer.colors.RED)
            check.append(1)
    if password:
        password = get_password_hash(password)        
        if database.update_user_password(session=session, username=username, password=password):
            typer.secho(f"User {username} password has been changed", fg=typer.colors.GREEN)
        else: 
            typer.secho(f"Failure in the update of user {username} password", fg=typer.colors.RED)
            check.append(2)
    if activated==True or activated==False: 
        if database.update_user_activated(session=session, username=username, activated=activated):
            typer.secho(f"User {username} activated state is now {activated}", fg=typer.colors.GREEN)
        else: 
            typer.secho(f"Failure in the update of user {username} activated state as : {activated}", fg=typer.colors.RED)
            check.append(3)
    if expirationDate:
        expirationDate=convert_string_to_date(expirationDate)
        if expirationDate == None:
            return typer.secho(f"Wrong format for expiration date", fg=typer.colors.RED)
        if expirationDate > datetime.date.today():
            user = database.get_a_single_user(session=session, username=username)
            if user:
                if not user.expiration_date or expirationDate > user.expiration_date:
                    if database.update_user_expiration_date(session=session, username=username, expirationDate=expirationDate):
                        return typer.secho(f"User {username} expiration date is now {expirationDate}", fg=typer.colors.GREEN)
                    else :
                        return typer.secho(f"Failure in the update of user {username} expiration date as : {expirationDate}", fg=typer.colors.RED)
                else :
                    return typer.secho(f"User {username} : the new expiration date is before the old expiration date. If you want to perform this operation use the command changedate", fg=typer.colors.RED)
            else:
                return typer.secho(f"User {username} not found", fg=typer.colors.RED)
        else:
            return typer.secho(f"User {username} : the new expiration date is before today. If you want to perform this operation use the command changedate",fg=typer.colors.RED)
    if not newUsername and not password and not expirationDate and activated!=True and activated!=False:
        return typer.secho(f"No modification of the user {username}", fg=typer.colors.RED)
    if 1 in check and 2 in check and 3 in check:
        return typer.secho(f"No modification of the user {username}", fg=typer.colors.RED)
 
def user_activate(session, username:str):
    if database.activate_user(session=session, username=username):
        return typer.secho(f"User {username} was activated", fg=typer.colors.GREEN)
    return typer.secho(f"Unsuccesfull activation of the user {username}", fg=typer.colors.RED)

def user_deactivate(session, username:str):
    if database.deactivate_user(session=session, username=username):
        return typer.secho(f"User {username} was deactivated", fg=typer.colors.GREEN)
    return typer.secho(f"Unsuccesfull deactivation of the user {username}", fg=typer.colors.RED)

def user_change_expiration_date(session, username:str, expirationDate:datetime.date):
    if not database.check_expiration_date(session=session, username=username, expirationDate=expirationDate):
        if ask_confirmation_expiration_date(session = session, expirationDate= expirationDate, username=username):
            database.change_expiration_date(session=session, username=username, expirationDate=expirationDate)
            typer.secho(f"User {username} expiration date is now {expirationDate}", fg=typer.colors.GREEN)
        else:
            typer.secho("Modification of expiration date cancelled", fg=typer.colors.RED)
            return False
    else: 
        if database.change_expiration_date(session=session, username=username, expirationDate=expirationDate): 
            typer.secho(f"User {username} expiration date is now {expirationDate}", fg=typer.colors.GREEN)
            return True

################ UTITLY FUNCTIONS ################

def convert_string_to_date(date:str):
    try:
        year, month, day = date.split('-')
        new_date = datetime.date(int(year), int(month), int(day))
        return new_date
    except (ValueError, AttributeError):
        return None
    except:
        return None
    
def ask_confirmation_expiration_date(session, expirationDate, username):
    confirmed = False
    valid_responses = {'yes', 'no'}
    while not confirmed:
        oldExpirationDate = database.user_expiration_date(session = session, username=username)
        user_input = input(f"You are going to update to an expiration date {expirationDate} which is before the actual one {oldExpirationDate}, do you confirm (yes/no): ").lower()
        if user_input in valid_responses:
            if user_input == 'yes':
                confirmed = True
            else:
                return False
        else:
            print("Invalid response. Answer with 'yes' ou 'no'.")
    return True

def ask_confirmation_delete_user(username):
    confirmed = False
    valid_responses = {'yes', 'no'}
    while not confirmed:
        user_input = input(f"You are going to delete {username}, do you confirm (yes/no): ").lower()
        if user_input in valid_responses:
            if user_input == 'yes':
                confirmed = True
            else:
                return False
        else:
            print("Invalid response. Answer with 'yes' ou 'no'.")
    return True

def get_password_hash(password):
    return pwd_context.hash(password)

def connect_to_db():
    username=os.getenv('username')  
    password=os.getenv('password')
    #password = get_password_hash(password) #2nd hash of the admin password used to connect to the DB
    global database_ip
    global database_name
    db : Session = database.start_a_db_session(
        DB_Username_For_Admin=username,
        DB_Password_For_Admin=password,
        DB_Name_For_Users_Tables=database_name,
        DB_Container_Name=database_ip
        )
    return db

def auto_logout():
    time.sleep(300)
    os.putenv('username', '')
    os.putenv('password', '')
    typer.secho(f"You are now disconnected, if you want to keep using the CLI you need to reconnect", fg=typer.colors.RED)
    os.system('bash')
    return exit

if __name__ == "__main__":
    app()





        