<?php
// Convenience entrypoint for an XAMPP checkout. Dedicated deployments should
// use web/ as the document root.
header('Location: web/', true, 302);
exit;
