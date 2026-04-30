async function companionPost(url, payload) {
  const token = window.localStorage.getItem("takeoff_companion_token") || "";
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Takeoff-Token": token
    },
    body: JSON.stringify(payload || {})
  });
  return response.json();
}
