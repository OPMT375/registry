// The chain page reads the class database with the PUBLIC key. Safe to commit: the database only allows reads with it.
// Supabase → Project Settings → API: copy the Project URL and the anon (public) key.
window.CHAIN = {
  url: '',          // e.g. 'https://abcdefghijkl.supabase.co'
  anonKey: '',      // the anon / publishable key, NOT the service_role key
  showPeople: true, // set to false to hide the "Who moved the chain" table
};
