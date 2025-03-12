.. image:: https://github.com/OCA/maintainer-tools/blob/master/template/module/icon.png
:alt: Odoo Community Association
:target: https://odoo-community.org

================
Payment Plaid

Integración de Odoo con Plaid para facilitar pagos bancarios y transferencias.

Este módulo proporciona la integración entre Odoo y Plaid <https://plaid.com/>_, permitiendo a los usuarios realizar pagos y transferencias bancarias de manera segura y eficiente.

Características

Conexión segura con Plaid para la autenticación de cuentas bancarias.

Posibilidad de seleccionar la cuenta bancaria deseada dentro de Odoo.

Procesamiento de pagos a través de la API de Plaid.

Manejo de errores y cancelaciones de usuario con mensajes amigables.

Instalación

Para instalar este módulo, simplemente agrégalo a tu directorio de addons y actualiza la lista de aplicaciones en Odoo.

Configuración

Regístrate en Plaid <https://plaid.com/>_ y obtén tus credenciales API.

Configura las credenciales en Ajustes > Métodos de Pago en Odoo.

Activa el método de pago Plaid en la configuración de pagos.

Uso

Al seleccionar el método de pago Plaid, el usuario será redirigido a la interfaz de Plaid para seleccionar una cuenta bancaria.

Una vez seleccionada la cuenta, el pago será procesado automáticamente.

Se mostrará el estado de la transacción en el historial de pagos de Odoo.

Desarrollo

Este módulo sigue los estándares de desarrollo de OCA. Para contribuir:

Clona el repositorio y crea una nueva rama para tus cambios.

Asegúrate de cumplir con las guías de estilo y convenciones de OCA.

Envía tu PR para revisión.

Créditos

Autor:

Odoo Community Association (OCA)

Mantenedor:

Este módulo es mantenido por la comunidad OCA.

Licencia:

Este módulo se publica bajo la licencia AGPL-3 <https://www.gnu.org/licenses/agpl-3.0.html>_.