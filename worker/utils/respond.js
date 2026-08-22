// Response formatting and error handling

function respondSuccess(data, command) {
  return {
    ok: true,
    command,
    data,
    timestamp: new Date().toISOString(),
  };
}

function respondError(error, statusCode = 500) {
  let code = "INTERNAL_ERROR";
  let message = error.message;

  if (statusCode === 400) {
    code = "BAD_REQUEST";
  } else if (statusCode === 401) {
    code = "UNAUTHORIZED";
  } else if (statusCode === 404) {
    code = "NOT_FOUND";
  } else if (statusCode === 429) {
    code = "RATE_LIMITED";
  }

  return {
    ok: false,
    error: message,
    code,
    timestamp: new Date().toISOString(),
  };
}

function respondEncrypted(encryptedData, signature) {
  return {
    encrypted_data: encryptedData,
    signature,
    timestamp: new Date().toISOString(),
  };
}

export { respondSuccess, respondError, respondEncrypted };
