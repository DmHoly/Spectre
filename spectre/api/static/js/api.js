/* Petit client HTTP partagé par toutes les pages : gère le cookie de session, le JSON, et
   redirige vers /connexion si la session a expiré (sauf pour l'appel qui vérifie justement si
   on est connecté). */

const api = {
  async request(path, options = {}) {
    const { redirectOn401 = true, ...rest } = options;
    const response = await fetch(path, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      ...rest,
      body: rest.body !== undefined ? JSON.stringify(rest.body) : undefined,
    });

    if (response.status === 401 && redirectOn401) {
      window.location.href = "/connexion?suite=" + encodeURIComponent(window.location.pathname);
      return new Promise(() => {});
    }

    let data = null;
    const text = await response.text();
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (e) {
        data = text;
      }
    }

    if (!response.ok) {
      const detail = data && typeof data === "object" ? data.detail : data;
      const message = typeof detail === "string" ? detail : "Une erreur est survenue.";
      const error = new Error(message);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    return data;
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
  del(path, options) {
    return this.request(path, { method: "DELETE", ...(options || {}) });
  },
};
