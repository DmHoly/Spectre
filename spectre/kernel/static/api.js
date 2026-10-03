/* Le client HTTP du noyau, partagé par toutes les pages : cookie de session, JSON, téléversement
   (FormData), réponses binaires, en-tête If-Match et ETag, erreurs lisibles, et redirection vers
   /connexion quand la session a expiré (sauf pour un appel qui vérifie justement si on est connecté :
   option redirectOn401: false). Aucune URL de l'API n'est écrite ici : chaque plugin les déclare
   dans son static/client.js (global <plugin>Api), qui passe par ces fonctions.

   Options de api.request (et des raccourcis get/post/put/patch/del/upload) :
     redirectOn401 (true)  - une réponse 401 renvoie vers /connexion?suite=<la page actuelle>
     as ("json")           - "blob" : le corps brut (une image, un fichier)
     ifMatch               - valeur de l'en-tête If-Match (la version affichée)
     withHeaders (false)   - true : renvoie {data, etag} au lieu de data seul
     formData              - un FormData envoyé tel quel (le navigateur pose le Content-Type) */

const API_PREFIX = "/api/";

// Le message d'une réponse en erreur : `detail` texte, un 422 FastAPI (tableau de {loc, msg}), ou un
// objet {message}.
function apiErrorMessage(data) {
  const detail = data && typeof data === "object" ? data.detail : data;
  if (typeof detail === "string" && detail) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => (item && typeof item === "object" ? item.msg || item.message : item)).filter(Boolean);
    if (messages.length) return messages.join(" · ");
  }
  if (detail && typeof detail === "object" && typeof detail.message === "string") return detail.message;
  return "Une erreur est survenue.";
}

const api = {
  async request(path, options = {}) {
    const { redirectOn401 = true, as = "json", ifMatch, withHeaders = false, formData, body, headers, ...rest } = options;
    const init = { credentials: "same-origin", ...rest, headers: { ...(headers || {}) } };
    if (formData !== undefined) {
      init.body = formData;
    } else {
      init.headers["Content-Type"] = "application/json";
      if (body !== undefined) init.body = JSON.stringify(body);
    }
    if (ifMatch) init.headers["If-Match"] = ifMatch;
    const response = await fetch(path, init);

    if (response.status === 401 && redirectOn401) {
      const here = window.location.pathname + window.location.search + window.location.hash;
      window.location.href = "/connexion?suite=" + encodeURIComponent(here);
      return new Promise(() => {});
    }

    let data = null;
    if (as === "blob" && response.ok) {
      data = await response.blob();
    } else {
      const text = await response.text();
      if (text) {
        try {
          data = JSON.parse(text);
        } catch (e) {
          data = text;
        }
      }
    }

    if (!response.ok) {
      const error = new Error(apiErrorMessage(data));
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return withHeaders ? { data, etag: response.headers.get("ETag") } : data;
  },

  get(path, options) {
    return this.request(path, { method: "GET", ...(options || {}) });
  },
  post(path, body, options) {
    return this.request(path, { method: "POST", body, ...(options || {}) });
  },
  put(path, body, options) {
    return this.request(path, { method: "PUT", body, ...(options || {}) });
  },
  patch(path, body, options) {
    return this.request(path, { method: "PATCH", body, ...(options || {}) });
  },
  del(path, options) {
    return this.request(path, { method: "DELETE", ...(options || {}) });
  },
  // Un téléversement multipart : `formData` part tel quel, sans Content-Type imposé.
  upload(path, formData, options) {
    return this.request(path, { method: "POST", formData, ...(options || {}) });
  },

  // `path` suivi de la query string des `params` définis (null, undefined et "" sont omis).
  withQuery(path, params) {
    const query = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value !== null && value !== undefined && value !== "") query.append(key, String(value));
    });
    const text = query.toString();
    return text ? `${path}?${text}` : path;
  },

  // Une URL servie par l'API de Spectre (une image, une pièce jointe) - pour la reconnaître dans
  // une page sans écrire son préfixe.
  isApiUrl(url) {
    return typeof url === "string" && url.startsWith(API_PREFIX);
  },
};
