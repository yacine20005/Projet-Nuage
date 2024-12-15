import flask
import db_yacine as db
#import db_liam as db
from passlib.context import CryptContext
from datetime import timedelta # Pour gérer la durée de la session
password_ctx = CryptContext(schemes=["bcrypt"]) # Création d'un objet pour gérer les mots de passe

app = flask.Flask(__name__)
app.secret_key = 'super_secret'
app.permanent_session_lifetime = timedelta(days=30)  # La session expirera après 30 jours
@app.context_processor
def inject_session():
    return dict(session=flask.session) # Permet d'accéder à la session dans les templates

@app.route("/")
def home():
    return flask.redirect(flask.url_for('boutique'))

@app.route("/boutique")
def boutique():
    conn = db.connect()
    cur = conn.cursor(cursor_factory=db.psycopg2.extras.NamedTupleCursor)
    cur.execute('SELECT * FROM Boutique;')
    jeux = cur.fetchall()
    cur.close()
    conn.close()
    return flask.render_template("boutique.html", jeux = jeux)

@app.route("/profil/<int:joueur_id>")
def profil(joueur_id):
    conn = db.connect()
    cur = conn.cursor(cursor_factory=db.psycopg2.extras.NamedTupleCursor)
    
    cur.execute("SELECT * FROM Joueur WHERE idJoueur = %s;", (joueur_id,))
    joueur = cur.fetchone()

    cur.execute("SELECT * FROM JoueurPossede WHERE JoueurPossede.idJoueur = %s;", (joueur_id,))
    possede = cur.fetchall()
    
    cur.execute("SELECT * FROM JoueurPartage WHERE JoueurPartage.idJoueurReceveur = %s;", (joueur_id,))
    partage = cur.fetchall()
    
    cur.execute("SELECT * FROM CommentaireJeu WHERE Joueur = %s;", (joueur_id,))
    commentaires = cur.fetchall()
    
    cur.execute("SELECT * FROM JoueurAmis WHERE idJoueur1 = %s", (joueur_id,))
    amis = cur.fetchall()
    infos_amis = [] # Dictionnaire pour stocker les informations des amis
    for ami in amis:
        if ami.idjoueur1 == flask.session["user_id"]:
            cur.execute("SELECT * FROM Joueur WHERE idJoueur = %s;", (ami.idjoueur2,))
            infos_amis.append(cur.fetchone())
    
    cur.execute("SELECT Jeu.idJeu, COUNT(Succes.idSucces) AS total_succes FROM Jeu LEFT JOIN Succes ON Jeu.idJeu = Succes.idJeu GROUP BY Jeu.idJeu;")
    liste_jeux = cur.fetchall()
    
    taux_completion_jeux = {}
    for jeu in liste_jeux:
        cur.execute("SELECT COUNT(*) AS succes_debloques FROM JoueurSucces JOIN Succes ON JoueurSucces.idSucces = Succes.idSucces WHERE JoueurSucces.idJoueur = %s AND Succes.idJeu = %s", (joueur_id, jeu.idjeu))
        succes_debloques = cur.fetchone().succes_debloques
        
        if jeu.total_succes > 0:
            taux_completion = (succes_debloques / jeu.total_succes) * 100
        else:
            taux_completion = 0
            
        taux_completion_jeux[jeu.idjeu] = taux_completion
    
    cur.close()
    conn.close()
    return flask.render_template("profil.html", possede=possede, partage=partage, commentaires=commentaires, joueur=joueur, taux_completion_jeux=taux_completion_jeux, infos_amis=infos_amis)

@app.route("/jeu/<int:id>")
def jeu(id):
    conn = db.connect()
    cur = conn.cursor(cursor_factory=db.psycopg2.extras.NamedTupleCursor)
    
    cur.execute("SELECT * FROM Boutique WHERE idjeu = %s;", (id,))  # Utilisation de paramètres préparés pour éviter l'injection SQL car psycopg2 se charge de gérer la valeur
    jeux = cur.fetchall()
        
    cur.execute("SELECT * FROM CommentaireJeu WHERE idjeu = %s;", (id,))
    commentaires = cur.fetchall()
    
    cur.close()
    conn.close()
    return flask.render_template("jeu.html", jeux=jeux, commentaires=commentaires)

@app.route("/deconnexion")
def deconnexion():
    flask.session.clear()  # Supprime 'user_id' de la session
    return flask.redirect(flask.url_for('boutique'))  # Redirige vers la boutique

@app.route('/recherche', methods=['GET'])
def recherche():
    resultats = []
    query = flask.request.args.get('recherche')
    if(query):
        type_recherche = flask.request.args.get('type-recherche')
        if(type_recherche in ["titre", "genres", "developpeur", "editeur"]):
            conn = db.connect()
            cur = conn.cursor(cursor_factory=db.psycopg2.extras.NamedTupleCursor)
            cur.execute(f"SELECT * FROM Boutique WHERE {type_recherche} ILIKE %s", ('%' + query + '%',)) # Utilisation de ilike pour ignorer la casse des caractères
            resultats = cur.fetchall()
            cur.close()
            conn.close()
    return flask.render_template("recherche.html", resultats=resultats)

@app.route("/connexion", methods=["GET", "POST"])
def connexion():
    conn = db.connect()
    cur = conn.cursor(cursor_factory=db.psycopg2.extras.NamedTupleCursor)
    etat = 0 # 0 si rien, 1 si pseudo/mail faux, 2 si mdp faux, 3 si connexion reussie!
    user = flask.request.form.get('user')
    password = flask.request.form.get('password')
    
    if user and password :
        etat = 1
        if '@' in user:
            cur.execute("SELECT idJoueur, mot_de_passe FROM Joueur WHERE email = %s;", (user,))
        else:
            cur.execute("SELECT idJoueur, mot_de_passe FROM Joueur WHERE pseudo = %s;", (user,))
        result = cur.fetchone()

        if result:
            etat = 2
            user_id = result.idjoueur
            user_hash = result.mot_de_passe
            verif_mdp = password_ctx.verify(password, user_hash)
            if verif_mdp:
                etat = 3
                flask.session.permanent = True
                flask.session['user_id'] = user_id
                
    cur.close()
    conn.close()
    if(etat != 3):
        return flask.render_template("connexion.html", etat = etat)
    else:
        return flask.redirect(flask.url_for('boutique'))
        



@app.route("/inscription", methods=["GET", "POST"])
def inscription():

    etat = 0  # 0 = pas d'erreur, 1 = email déjà utilisé, 2 = pseudo déjà utilisé ou trop long, 3 = mot de passe trop court
    conn = db.connect()
    cur = conn.cursor(cursor_factory=db.psycopg2.extras.NamedTupleCursor)
    
    nom = flask.request.form.get('nom')
    email = flask.request.form.get('email')
    user = flask.request.form.get('user')
    password = flask.request.form.get('password')
    datenaissance = flask.request.form.get('date_de_naissance')
    
    if(nom and email and user and password and datenaissance):
        if '@' in email and  '.' in email:
            cur.execute("SELECT idJoueur FROM Joueur WHERE email = %s;", (email,))
            if(cur.fetchone()):
                etat = 1
                return flask.render_template("inscription.html", etat = etat)
            
            cur.execute("SELECT idJoueur FROM Joueur WHERE pseudo = %s;", (user,))
            if(cur.fetchone() or len(user) < 3 or len(user) > 16):
                etat = 2
                return flask.render_template("inscription.html", etat = etat)
            
            if(len(password) < 8):
                etat = 3
                return flask.render_template("inscription.html", etat = etat)
            
            if etat == 0:
                cur.execute("SELECT MAX(idJoueur) FROM Joueur;")
                max_id = cur.fetchone()
                if max_id is None:
                    max_id = 0
                else:
                    new_id = max_id.max + 1
                
                hash_pw = password_ctx.hash(password) #Calcul du hash du mot de passe à stocker
                cur.execute("INSERT INTO Joueur (idJoueur, pseudo, email, mot_de_passe, nom, date_naissance, solde) VALUES (%s ,%s, %s, %s, %s, %s, 0);", (new_id ,user, email, hash_pw, nom, datenaissance))
            cur.close()
            conn.close()
            
        if etat == 0:
            return flask.redirect(flask.url_for('connexion'))
        
    return flask.render_template("inscription.html", etat = etat)


if __name__ == '__main__':
    app.run(debug=True)
