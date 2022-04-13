# Copyright 2022 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Experimental GDC-H credentials support."""

import base64

import six
from six.moves import http_client

from google.auth import _helpers
from google.auth import credentials
from google.auth import exceptions
from google.oauth2 import _client


TOKEN_EXCHANGE_TYPE = "urn:ietf:params:oauth:token-type:token-exchange"
ACCESS_TOKEN_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:access_token"
JWT_TOKEN_TYPE = "urn:ietf:params:oauth:token-type:jwt"
SERVICE_ACCOUNT_TOKEN_TYPE = "urn:k8s:params:oauth:token-type:serviceaccount"


class Credentials(credentials.CredentialsWithQuotaProject):
    """Credentials for GCD-H.
    """

    def __init__(
        self,
        k8s_ca_cert_path,
        k8s_cert_path,
        k8s_key_path,
        k8s_token_endpoint,
        ais_ca_cert_path,
        ais_token_endpoint,
        audience,
        quota_project_id=None,
    ):
        """
        Args:
            k8s_ca_cert_path (str): CA cert path for k8s calls
            k8s_cert_path (str): Certificate path for k8s calls
            k8s_key_path (str): Key path for k8s calls
            k8s_token_endpoint (str): k8s token endpoint url
            ais_ca_cert_path (str): CA cert path for AIS token endpoint calls
            ais_token_endpoint (str): AIS token endpoint url
            audience (str): The audience for the requested AIS token
        Raises:
            ValueError: If the provided API key is not a non-empty string.
        """
        super(Credentials, self).__init__()
        self._k8s_ca_cert_path = k8s_ca_cert_path
        self._k8s_cert_path = k8s_cert_path
        self._k8s_key_path = k8s_key_path
        self._k8s_token_endpoint = k8s_token_endpoint
        self._ais_ca_cert_path = ais_ca_cert_path
        self._ais_token_endpoint = ais_token_endpoint
        self._audience = audience
        self._quota_project_id = quota_project_id

    def _make_k8s_token_request(self, request):
        # mTLS connection to k8s token endpoint to get a k8s token.
        k8s_response_data = _client._token_endpoint_request(
            request,
            self._k8s_token_endpoint,
            {},
            None,
            True,
            (self._k8s_cert_path, self._k8s_key_path),
            self._k8s_ca_cert_path,
            http_client.CREATED,
        )

        try:
            k8s_token = k8s_response_data["status"]["token"]
            print("received k8s token: {}".format(k8s_token))
            return k8s_token
        except KeyError as caught_exc:
            new_exc = exceptions.RefreshError(
                "No access token in k8s token response.", k8s_response_data
            )
            six.raise_from(new_exc, caught_exc)

    def _make_ais_token_request(self, k8s_token, request):
        k8s_token = base64.b64encode(k8s_token.encode()).decode()

        # send a request to AIS token point with the k8s token
        ais_request_body = {
            "grant_type": TOKEN_EXCHANGE_TYPE,
            "audience": self._audience,
            "requested_token_type": ACCESS_TOKEN_TOKEN_TYPE,
            "subject_token": k8s_token,
            "subject_token_type": SERVICE_ACCOUNT_TOKEN_TYPE,
        }
        ais_response_data = _client._token_endpoint_request(
            request,
            self._ais_token_endpoint,
            ais_request_body,
            None,
            True,
            None,
            self._ais_ca_cert_path,
        )
        ais_token, _, ais_expiry, _ = _client._handle_refresh_grant_response(
            ais_response_data, None
        )
        print("received ais token: {}".format(ais_token))
        return ais_token, ais_expiry

    @_helpers.copy_docstring(credentials.Credentials)
    def refresh(self, request):
        k8s_token = self._make_k8s_token_request(request)
        self.token, self.expiry = self._make_ais_token_request(k8s_token, request)

    def with_audience(self, audience):
        """Create a copy of GDCH credentials with the specified audience.

        Args:
            audience (str): The intended audience for GDCH credentials.
        """
        return self.__class__(
            self._k8s_ca_cert_path,
            self._k8s_cert_path,
            self._k8s_key_path,
            self._k8s_token_endpoint,
            self._ais_ca_cert_path,
            self._ais_token_endpoint,
            audience,
            self._quota_project_id,
        )

    @_helpers.copy_docstring(credentials.CredentialsWithQuotaProject)
    def with_quota_project(self, quota_project_id):
        return self.__class__(
            self._k8s_ca_cert_path,
            self._k8s_cert_path,
            self._k8s_key_path,
            self._k8s_token_endpoint,
            self._ais_ca_cert_path,
            self._ais_token_endpoint,
            self._audience,
            quota_project_id,
        )
