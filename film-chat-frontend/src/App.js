import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import './App.css';

// ─────────────────────────────────────────────────────────────
// Cinémathèque — un curatore di film a portata di conversazione.
// Sistema multilingua: IT / EN / ES / FR / DE
// ─────────────────────────────────────────────────────────────

// Dizionario UI completo per tutte le lingue
const UI_STRINGS = {
  it: {
    // Masthead
    masthead_tagline: "Un curatore a portata di conversazione · Anno IV · N°",
    nav_dialogue: "Dialogo",
    nav_archive: "Archivio",
    nav_lists: "Liste",
    nav_account: "Account",
    
    // Welcome
    welcome_eyebrow: "Editoriale · Buonasera",
    welcome_title: "Cosa <em>vorresti</em> guardare<br/>stasera?",
    welcome_lede: "Sono un curatore. Conosco l'archivio, so dove i film sono disponibili, e ho opinioni — usale o ignorale. Comincia con un'idea, anche vaga.",
    
    // Quick prompts
    prompts: [
      "Qualcosa di leggero per stasera, niente impegnativo",
      "Un thriller psicologico come Anatomia di una caduta",
      "Drammi sussurrati, dialoghi più che esplosioni",
      "Cosa è uscito di buono questo mese?",
    ],
    
    // Composer
    composer_label: "Chiedi —",
    composer_placeholder: "Dimmi cosa cerchi, un titolo, un'epoca, un attore…",
    composer_submit: "Invia",
    composer_thinking: "Sto pensando",
    
    // Turn labels
    turn_you: "Tu —",
    turn_curator: "Curatore —",
    
    // Film list
    films_one: "Una proposta",
    films_many: "proposte",
    films_curated: "curate dal Curatore",
    films_sorted: "ordinate per affinità",
    
    // Film card
    film_available: "Disponibile su",
    film_not_streaming: "Non in streaming",
    film_watch_on: "Guarda su",
    
    // Status
    status_connecting: "Connessione…",
    status_thinking: "Consulto l'archivio…",
    
    // Error
    error_connection: "Connessione interrotta. Verifica che il backend sia in esecuzione.",
  },
  
  en: {
    // Masthead
    masthead_tagline: "A curator at your fingertips · Year IV · N°",
    nav_dialogue: "Dialogue",
    nav_archive: "Archive",
    nav_lists: "Lists",
    nav_account: "Account",
    
    // Welcome
    welcome_eyebrow: "Editorial · Good evening",
    welcome_title: "What would you <em>like</em><br/>to watch tonight?",
    welcome_lede: "I'm a curator. I know the archive, I know where films are available, and I have opinions — use them or ignore them. Start with an idea, even a vague one.",
    
    // Quick prompts
    prompts: [
      "Something light for tonight, nothing demanding",
      "A psychological thriller like Anatomy of a Fall",
      "Whispered dramas, dialogue over explosions",
      "What good releases came out this month?",
    ],
    
    // Composer
    composer_label: "Ask —",
    composer_placeholder: "Tell me what you're looking for: a title, an era, an actor…",
    composer_submit: "Send",
    composer_thinking: "Thinking",
    
    // Turn labels
    turn_you: "You —",
    turn_curator: "Curator —",
    
    // Film list
    films_one: "One suggestion",
    films_many: "suggestions",
    films_curated: "curated by the Curator",
    films_sorted: "sorted by relevance",
    
    // Film card
    film_available: "Available on",
    film_not_streaming: "Not on streaming",
    film_watch_on: "Watch on",
    
    // Status
    status_connecting: "Connecting…",
    status_thinking: "Consulting the archive…",
    
    // Error
    error_connection: "Connection interrupted. Please check that the backend is running.",
  },
  
  es: {
    // Masthead
    masthead_tagline: "Un curador al alcance de la mano · Año IV · N°",
    nav_dialogue: "Diálogo",
    nav_archive: "Archivo",
    nav_lists: "Listas",
    nav_account: "Cuenta",
    
    // Welcome
    welcome_eyebrow: "Editorial · Buenas noches",
    welcome_title: "¿Qué te <em>gustaría</em><br/>ver esta noche?",
    welcome_lede: "Soy un curador. Conozco el archivo, sé dónde están disponibles las películas y tengo opiniones — úsalas o ignóralas. Empieza con una idea, incluso vaga.",
    
    // Quick prompts
    prompts: [
      "Algo ligero para esta noche, nada exigente",
      "Un thriller psicológico como Anatomía de una caída",
      "Dramas susurrados, diálogos más que explosiones",
      "¿Qué bueno salió este mes?",
    ],
    
    // Composer
    composer_label: "Pregunta —",
    composer_placeholder: "Dime qué buscas: un título, una época, un actor…",
    composer_submit: "Enviar",
    composer_thinking: "Pensando",
    
    // Turn labels
    turn_you: "Tú —",
    turn_curator: "Curador —",
    
    // Film list
    films_one: "Una sugerencia",
    films_many: "sugerencias",
    films_curated: "curadas por el Curador",
    films_sorted: "ordenadas por afinidad",
    
    // Film card
    film_available: "Disponible en",
    film_not_streaming: "No en streaming",
    film_watch_on: "Ver en",
    
    // Status
    status_connecting: "Conectando…",
    status_thinking: "Consultando el archivo…",
    
    // Error
    error_connection: "Conexión interrumpida. Verifica que el backend esté ejecutándose.",
  },
  
  fr: {
    // Masthead
    masthead_tagline: "Un curateur à portée de main · Année IV · N°",
    nav_dialogue: "Dialogue",
    nav_archive: "Archive",
    nav_lists: "Listes",
    nav_account: "Compte",
    
    // Welcome
    welcome_eyebrow: "Éditorial · Bonsoir",
    welcome_title: "Qu'aimeriez-vous <em>regarder</em><br/>ce soir?",
    welcome_lede: "Je suis un curateur. Je connais l'archive, je sais où les films sont disponibles, et j'ai des opinions — utilisez-les ou ignorez-les. Commencez avec une idée, même vague.",
    
    // Quick prompts
    prompts: [
      "Quelque chose de léger pour ce soir, rien d'exigeant",
      "Un thriller psychologique comme Anatomie d'une chute",
      "Drames chuchotés, dialogues plutôt qu'explosions",
      "Quelles bonnes sorties ce mois-ci?",
    ],
    
    // Composer
    composer_label: "Demandez —",
    composer_placeholder: "Dites-moi ce que vous cherchez: un titre, une époque, un acteur…",
    composer_submit: "Envoyer",
    composer_thinking: "Je réfléchis",
    
    // Turn labels
    turn_you: "Vous —",
    turn_curator: "Curateur —",
    
    // Film list
    films_one: "Une suggestion",
    films_many: "suggestions",
    films_curated: "sélectionnés par le Curateur",
    films_sorted: "triés par pertinence",
    
    // Film card
    film_available: "Disponible sur",
    film_not_streaming: "Pas en streaming",
    film_watch_on: "Regarder sur",
    
    // Status
    status_connecting: "Connexion…",
    status_thinking: "Consultation de l'archive…",
    
    // Error
    error_connection: "Connexion interrompue. Vérifiez que le backend fonctionne.",
  },
  
  de: {
    // Masthead
    masthead_tagline: "Ein Kurator zum Greifen nah · Jahr IV · N°",
    nav_dialogue: "Dialog",
    nav_archive: "Archiv",
    nav_lists: "Listen",
    nav_account: "Konto",
    
    // Welcome
    welcome_eyebrow: "Editorial · Guten Abend",
    welcome_title: "Was möchten Sie <em>heute Abend</em><br/>sehen?",
    welcome_lede: "Ich bin ein Kurator. Ich kenne das Archiv, ich weiß wo Filme verfügbar sind, und ich habe Meinungen — nutzen Sie sie oder ignorieren Sie sie. Beginnen Sie mit einer Idee, auch einer vagen.",
    
    // Quick prompts
    prompts: [
      "Etwas Leichtes für heute Abend, nichts Anspruchsvolles",
      "Ein Psychothriller wie Anatomie eines Falls",
      "Geflüsterte Dramen, Dialoge statt Explosionen",
      "Was kam diesen Monat Gutes heraus?",
    ],
    
    // Composer
    composer_label: "Fragen —",
    composer_placeholder: "Sagen Sie mir, wonach Sie suchen: ein Titel, eine Epoche, ein Schauspieler…",
    composer_submit: "Senden",
    composer_thinking: "Denke nach",
    
    // Turn labels
    turn_you: "Sie —",
    turn_curator: "Kurator —",
    
    // Film list
    films_one: "Ein Vorschlag",
    films_many: "Vorschläge",
    films_curated: "kuratiert vom Kurator",
    films_sorted: "nach Relevanz sortiert",
    
    // Film card
    film_available: "Verfügbar auf",
    film_not_streaming: "Nicht im Streaming",
    film_watch_on: "Ansehen auf",
    
    // Status
    status_connecting: "Verbindung…",
    status_thinking: "Konsultiere das Archiv…",
    
    // Error
    error_connection: "Verbindung unterbrochen. Überprüfen Sie, ob das Backend läuft.",
  }
};

function App() {
  // Language state - load from localStorage or default to 'it'
  const [language, setLanguage] = useState(() => {
    return localStorage.getItem('filmchat_language') || 'it';
  });
  
  const [messages, setMessages] = useState([{ role: 'assistant', content: '', films: [], statusUpdates: [], isWelcome: true }]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);

  // Helper to get translated string
  const t = (key) => UI_STRINGS[language]?.[key] || UI_STRINGS['it'][key];

  // Save language preference
  const changeLanguage = (newLang) => {
    setLanguage(newLang);
    localStorage.setItem('filmchat_language', newLang);
  };

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const sendMessage = async (overrideText) => {
    const text = (overrideText ?? input).trim();
    if (!text || loading) return;

    const userMessage = { role: 'user', content: text };
    setMessages(prev => {
      const base = prev.filter(m => !m.isWelcome);
      return [...base, userMessage];
    });
    setInput('');
    setLoading(true);

    setMessages(prev => [...prev, {
      role: 'assistant',
      content: '',
      films: [],
      status: t('status_connecting'),
      statusUpdates: [],
    }]);

    try {
      const history = messages
        .filter(m => m.role !== 'system' && !m.isWelcome)
        .concat([userMessage]);

      const response = await fetch('http://localhost:8000/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          conversation_history: history.slice(0, -1),
          language: language,  // ← PASS LANGUAGE TO BACKEND
        }),
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            setMessages(prev => {
              const next = [...prev];
              const i = next.length - 1;
              const cur = next[i];

              const seen = (kind, t) =>
                cur.statusUpdates.some(u => u.text === t && u.type === kind);

              if (data.type === 'status') {
                next[i] = {
                  ...cur,
                  status: data.message,
                  statusUpdates: seen('status', data.message)
                    ? cur.statusUpdates
                    : [...cur.statusUpdates, { type: 'status', text: data.message, timestamp: Date.now() }],
                };
              } else if (data.type === 'tool_call') {
                next[i] = {
                  ...cur,
                  status: data.message,
                  statusUpdates: seen('tool', data.message)
                    ? cur.statusUpdates
                    : [...cur.statusUpdates, { type: 'tool', text: data.message, tool: data.tool, timestamp: Date.now() }],
                };
              } else if (data.type === 'tool_result') {
                next[i] = {
                  ...cur,
                  statusUpdates: seen('result', data.message)
                    ? cur.statusUpdates
                    : [...cur.statusUpdates, { type: 'result', text: data.message, tool: data.tool, timestamp: Date.now() }],
                };
              } else if (data.type === 'complete') {
                next[i] = {
                  ...cur,
                  content: data.text,
                  films: [...(data.films || [])],
                  status: null,
                };
              } else if (data.type === 'error') {
                next[i] = {
                  ...cur,
                  content: data.message,
                  films: [],
                  status: null,
                  error: true,
                };
              }
              return next;
            });
          } catch (e) {
            console.error('Parse error:', e);
          }
        }
      }
    } catch (error) {
      console.error('Error:', error);
      setMessages(prev => {
        const next = [...prev];
        const i = next.length - 1;
        next[i] = {
          ...next[i],
          content: t('error_connection'),
          films: [],
          status: null,
          error: true,
        };
        return next;
      });
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const issueNo = String(247 + messages.filter(m => m.role === 'user').length).padStart(3, '0');

  return (
    <div className="app">
      {/* Masthead */}
      <header className="masthead">
        <div className="masthead-inner">
          <div className="brand">
            <div className="brand-mark">
              Cinémathèque<span className="brand-dot">.</span>
            </div>
            <div className="brand-tag">
              {t('masthead_tagline')} {issueNo}
            </div>
          </div>
          <nav className="masthead-nav">
            <button className="nav-link is-active">{t('nav_dialogue')}</button>
            <button className="nav-link">{t('nav_archive')}</button>
            <button className="nav-link">{t('nav_lists')}</button>
            <button className="nav-link">{t('nav_account')}</button>
            <div className="nav-divider" />
            <LanguageSelector language={language} onChange={changeLanguage} />
          </nav>
        </div>
      </header>

      {/* Conversation */}
      <main className="conversation" ref={scrollRef}>
        <div className="conversation-inner">
          {messages.map((msg, idx) => {
            if (msg.isWelcome) return <WelcomeState key="w" onPick={(p) => sendMessage(p)} t={t} />;
            if (msg.role === 'user') return <UserTurn key={idx} text={msg.content} t={t} />;
            return <CuratorTurn key={idx} msg={msg} t={t} />;
          })}
        </div>
      </main>

      {/* Composer */}
      <footer className="composer">
        <div className="composer-inner">
          <label className="composer-label" htmlFor="ask">{t('composer_label')}</label>
          <input
            id="ask"
            ref={inputRef}
            className="composer-input"
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('composer_placeholder')}
            disabled={loading}
            autoFocus
          />
          <button
            className="composer-submit"
            onClick={() => sendMessage()}
            disabled={loading || !input.trim()}
          >
            {loading ? t('composer_thinking') : t('composer_submit')} <span aria-hidden>➜</span>
          </button>
        </div>
      </footer>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Language Selector Component - Ultra-minimal editorial
// ─────────────────────────────────────────────────────────────
function LanguageSelector({ language, onChange }) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);
  
  const languages = [
    { code: 'it', label: 'Italiano' },
    { code: 'en', label: 'English' },
    { code: 'es', label: 'Español' },
    { code: 'fr', label: 'Français' },
    { code: 'de', label: 'Deutsch' },
  ];
  
  const currentLang = languages.find(l => l.code === language) || languages[0];
  
  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);
  
  const handleSelect = (code) => {
    onChange(code);
    setIsOpen(false);
  };
  
  return (
    <div className="language-selector" ref={dropdownRef}>
      <button 
        className="language-trigger"
        onClick={() => setIsOpen(!isOpen)}
        aria-label="Select language"
        aria-expanded={isOpen}
      >
        {currentLang.code.toUpperCase()}
      </button>
      
      {isOpen && (
        <div className="language-menu">
          {languages.map((lang) => (
            <button
              key={lang.code}
              className={`language-item ${lang.code === language ? 'is-current' : ''}`}
              onClick={() => handleSelect(lang.code)}
            >
              {lang.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Welcome State
// ─────────────────────────────────────────────────────────────
function WelcomeState({ onPick, t }) {
  const prompts = t('prompts');
  
  return (
    <div className="welcome">
      <div className="welcome-eyebrow">{t('welcome_eyebrow')}</div>
      <h1 className="welcome-title" dangerouslySetInnerHTML={{ __html: t('welcome_title') }} />
      <p className="welcome-lede">{t('welcome_lede')}</p>
      <div className="welcome-prompts">
        {prompts.map((p, i) => (
          <button key={i} className="prompt-chip" onClick={() => onPick(p)}>
            <span className="prompt-no">{String(i + 1).padStart(2, '0')}</span>
            <span className="prompt-text">{p}</span>
            <span className="prompt-arrow" aria-hidden>↗</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// User Turn
// ─────────────────────────────────────────────────────────────
function UserTurn({ text, t }) {
  return (
    <article className="turn turn--user">
      <div className="turn-label">{t('turn_you')}</div>
      <div className="turn-body">
        <blockquote className="user-quote">"{text}"</blockquote>
      </div>
    </article>
  );
}

// ─────────────────────────────────────────────────────────────
// Curator Turn
// ─────────────────────────────────────────────────────────────
function CuratorTurn({ msg, t }) {
  const hasFilms = msg.films && msg.films.length > 0;
  const isThinking = !msg.content && (msg.status || msg.statusUpdates.length > 0);

  return (
    <article className="turn turn--curator">
      <div className="turn-label turn-label--accent">{t('turn_curator')}</div>
      <div className="turn-body">

        {msg.statusUpdates.length > 0 && (
          <div className="agent-trace">
            {msg.statusUpdates.map((u, i) => (
              <div key={i} className={`trace-line trace-line--${u.type}`}>
                <span className="trace-glyph">
                  {u.type === 'result' ? '✓' : u.type === 'tool' ? '⁂' : '·'}
                </span>
                {u.tool && <code className="trace-tool">{u.tool}</code>}
                <span className="trace-text">{u.text}</span>
              </div>
            ))}
          </div>
        )}

        {isThinking && !msg.content && (
          <div className="thinking">
            <span className="thinking-dot" />
            <span>{msg.status || t('status_thinking')}</span>
          </div>
        )}

        {msg.content && (
          <div className={`curator-prose ${hasFilms ? 'with-drop-cap' : ''} ${msg.error ? 'is-error' : ''}`}>
            <ReactMarkdown>{msg.content}</ReactMarkdown>
          </div>
        )}

        {hasFilms && <FilmList films={msg.films} t={t} />}
      </div>
    </article>
  );
}

// ─────────────────────────────────────────────────────────────
// Film List
// ─────────────────────────────────────────────────────────────
function FilmList({ films, t }) {
  return (
    <section className="film-list">
      <header className="film-list-head">
        <div className="film-list-title">
          {films.length === 1 ? t('films_one') : `${films.length} ${t('films_many')}`} · {t('films_curated')}
        </div>
        <div className="film-list-meta">{t('films_sorted')}</div>
      </header>

      <div className="film-grid">
        {films.map((f, i) => (
          <FilmCard key={f.id || i} film={f} index={i} t={t} />
        ))}
      </div>
    </section>
  );
}

function FilmCard({ film, index, t }) {
  return (
    <article className="film-card">
      <a
        className="film-poster"
        href={film.link}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={film.title}
      >
        {film.poster ? (
          <img src={film.poster} alt={film.title} loading="lazy" />
        ) : (
          <div className="film-poster-fallback">
            <span>{film.title}</span>
          </div>
        )}
        <span className="film-no">N° {String(index + 1).padStart(2, '0')}</span>
      </a>

      <a
        href={film.link}
        target="_blank"
        rel="noopener noreferrer"
        className="film-title"
      >
        {film.title}
      </a>

      <div className="film-meta">
        {film.year && <span className="film-year">{film.year}</span>}
        {film.rating != null && <> · <span className="film-rating">★ {Number(film.rating).toFixed(1)}</span></>}
        {film.genres && film.genres.length > 0 && (
          <div className="film-genres">{film.genres.slice(0, 2).join(' · ')}</div>
        )}
      </div>

      <div className="film-streaming">
        {film.streaming && film.streaming.length > 0 ? (
          <>
            <div className="streaming-label">{t('film_available')}</div>
            <div className="streaming-badges">
              {film.streaming.map((p, i) => (
                <a
                  key={i}
                  href={p.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="platform-badge"
                  title={`${t('film_watch_on')} ${p.name}`}
                >
                  {p.logo
                    ? <img src={p.logo} alt={p.name} />
                    : <span>{p.name}</span>}
                </a>
              ))}
            </div>
          </>
        ) : (
          <div className="streaming-label streaming-label--muted">{t('film_not_streaming')}</div>
        )}
      </div>
    </article>
  );
}

export default App;
