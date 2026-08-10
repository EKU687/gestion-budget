from supabase import create_client

print("--- TEST DE CONNEXION SUPABASE ---")

# 1. Tes clés secrètes (remplace avec TES vraies clés)
url = "https://icjcseqyhlymfqcchlyl.supabase.co"
key = "sb_publishable_528qPZh4CGs5aHAtk9tTzA_NWVtUOA9"

# 2. On crée le pont de communication (le client)
mon_pont_supabase = create_client(url, key)

print("⏳ Tentative de connexion en cours...")

# 3. On fait une requête : on demande à lire tout ce qu'il y a dans la table 'budgets'
try:
    # La méthode .table() choisit la feuille, .select("*") veut dire "prends toutes les colonnes"
    reponse = mon_pont_supabase.table("Budget").select("*").execute()
    
    print("✅ Connexion réussie !")
    print("Voici le contenu actuel de ta base de données :")
    print(reponse.data)
    
except Exception as erreur:
    print("❌ Aïe, la connexion a échoué. Voici l'erreur :")
    print(erreur)