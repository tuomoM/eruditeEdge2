DELETE FROM access_requests
WHERE id NOT IN (
    SELECT MAX(id)
    FROM access_requests
    GROUP BY email
);

CREATE UNIQUE INDEX access_requests_email_unique
ON access_requests(email);
