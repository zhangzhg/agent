import request from "@/utils/request";

export function getConversations() {
  return request({
    url: "/chat/conversations",
    method: "get",
  });
}

export function getConversation(id) {
  return request({
    url: `/chat/conversations/${id}`,
    method: "get",
  });
}

export function createConversation(title) {
  return request({
    url: "/chat/conversations",
    method: "post",
    params: { title },
  });
}

export function deleteConversation(id) {
  return request({
    url: `/chat/conversations/${id}`,
    method: "delete",
  });
}

export function streamChat(
  conversationId,
  message,
  onMessage,
  onConversationId,
  onDone,
  onError,
) {
  const token = localStorage.getItem("token");

  fetch("/api/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      conversationId,
      message,
    }),
  })
    .then((response) => {
      // 先判断 HTTP 状态码
      if (response.status !== 200) {
        throw new Error(`HTTP 错误: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      function read() {
        reader
          .read()
          .then(({ done, value }) => {
            if (done) {
              onDone();
              return;
            }

            const text = decoder.decode(value);
            const lines = text.split("\n");

            let eventType = "";

            lines.forEach((line) => {
              if (line.startsWith("event:")) {
                eventType = line.substring(6).trim();
              } else if (line.startsWith("data:")) {
                const data = line.substring(5).trim();

                if (eventType === "message") {
                  onMessage(data);
                } else if (eventType === "conversationId") {
                  onConversationId(parseInt(data));
                } else if (eventType === "done") {
                  onDone();
                }
              }
            });

            read();
          })
          .catch((error) => {
            onError(error);
          });
      }

      read();
    })
    .catch((error) => {
      onError(error);
    });
}
